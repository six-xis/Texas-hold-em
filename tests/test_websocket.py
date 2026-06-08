from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.room_service import RoomService
from app.services.websocket_manager import WebSocketManager


def test_websocket_join_and_room_state_updates() -> None:
    client = TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )
    created = client.post("/api/rooms", json={"nickname": "Host"}).json()
    room_code = created["room"]["room_code"]

    with client.websocket_connect(f"/ws/rooms/{room_code}") as websocket:
        connected = websocket.receive_json()
        assert connected["type"] == "connected"

        websocket.send_json(
            {
                "type": "join_room",
                "request_id": "join-1",
                "payload": {
                    "room_code": room_code,
                    "nickname": "Alice",
                },
            }
        )
        joined = websocket.receive_json()
        assert joined["type"] == "room_state"
        guest_id = joined["payload"]["viewer"]["guest_id"]

        websocket.send_json(
            {
                "type": "sit_down",
                "request_id": "sit-1",
                "payload": {
                    "seat_index": 3,
                    "guest_id": guest_id,
                },
            }
        )
        seated = websocket.receive_json()

        assert seated["type"] == "room_state"
        assert seated["payload"]["viewer"]["seat_index"] == 3
        assert seated["payload"]["seats"][3]["occupied"] is True
        assert seated["payload"]["seats"][3]["nickname"] == "Alice"


def test_websocket_invalid_payload_returns_error() -> None:
    client = TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )
    created = client.post("/api/rooms", json={"nickname": "Host"}).json()
    room_code = created["room"]["room_code"]

    with client.websocket_connect(f"/ws/rooms/{room_code}") as websocket:
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "join_room",
                "payload": {"room_code": room_code, "nickname": "Alice"},
            }
        )
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "sit_down",
                "request_id": "bad-seat",
                "payload": {"seat_index": True},
            }
        )
        error = websocket.receive_json()

        assert error["type"] == "action_error"
        assert error["request_id"] == "bad-seat"
        assert error["payload"]["code"] == "INVALID_PAYLOAD"


def test_websocket_host_can_pause_and_end_game() -> None:
    client = TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )
    created = client.post(
        "/api/rooms",
        json={"nickname": "Alice", "small_blind": 5, "big_blind": 10},
    ).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]
    bob_id = client.post(
        f"/api/rooms/{room_code}/join",
        json={"nickname": "Bob"},
    ).json()["guest"]["guest_id"]

    client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": alice_id, "seat_index": 0},
    )
    client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": bob_id, "seat_index": 1},
    )
    client.post(
        f"/api/rooms/{room_code}/ready",
        json={"guest_id": alice_id, "is_ready": True},
    )
    client.post(
        f"/api/rooms/{room_code}/ready",
        json={"guest_id": bob_id, "is_ready": True},
    )
    client.post(f"/api/rooms/{room_code}/start", json={"guest_id": alice_id})

    with client.websocket_connect(f"/ws/rooms/{room_code}?guest_id={alice_id}") as websocket:
        initial_state = websocket.receive_json()
        assert initial_state["type"] == "room_state"
        assert initial_state["payload"]["status"] == "playing"

        websocket.send_json(
            {
                "type": "pause_game",
                "request_id": "pause-1",
                "payload": {"is_paused": True},
            }
        )
        paused = websocket.receive_json()
        assert paused["type"] == "room_state"
        assert paused["payload"]["is_paused"] is True
        assert paused["payload"]["viewer"]["can_act"] is False

        websocket.send_json(
            {
                "type": "end_game",
                "request_id": "end-1",
                "payload": {},
            }
        )
        ended = websocket.receive_json()
        assert ended["type"] == "room_state"
        assert ended["payload"]["status"] == "waiting"
        assert ended["payload"]["is_paused"] is False


def test_websocket_chat_message_is_broadcast_to_room() -> None:
    client = TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )
    created = client.post("/api/rooms", json={"nickname": "Alice"}).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]
    bob_id = client.post(
        f"/api/rooms/{room_code}/join",
        json={"nickname": "Bob"},
    ).json()["guest"]["guest_id"]

    with client.websocket_connect(f"/ws/rooms/{room_code}?guest_id={alice_id}") as alice_ws:
        assert alice_ws.receive_json()["type"] == "room_state"
        with client.websocket_connect(f"/ws/rooms/{room_code}?guest_id={bob_id}") as bob_ws:
            assert bob_ws.receive_json()["type"] == "room_state"

            alice_ws.send_json(
                {
                    "type": "send_chat_message",
                    "request_id": "chat-1",
                    "payload": {"content": "大家好"},
                }
            )

            alice_chat = _receive_until(alice_ws, "chat_message")
            bob_chat = _receive_until(bob_ws, "chat_message")

            assert alice_chat["payload"]["content"] == "大家好"
            assert bob_chat["payload"]["content"] == "大家好"
            assert bob_chat["payload"]["guest_id"] == alice_id


def test_websocket_host_can_toggle_ai_for_room() -> None:
    client = TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )
    created = client.post("/api/rooms", json={"nickname": "Alice"}).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]
    bob_id = client.post(
        f"/api/rooms/{room_code}/join",
        json={"nickname": "Bob"},
    ).json()["guest"]["guest_id"]

    with client.websocket_connect(f"/ws/rooms/{room_code}?guest_id={alice_id}") as alice_ws:
        assert alice_ws.receive_json()["type"] == "room_state"
        with client.websocket_connect(f"/ws/rooms/{room_code}?guest_id={bob_id}") as bob_ws:
            assert bob_ws.receive_json()["type"] == "room_state"

            alice_ws.send_json(
                {
                    "type": "set_ai_enabled",
                    "request_id": "ai-1",
                    "payload": {"is_enabled": True},
                }
            )

            alice_state = _receive_room_state_with_ai(alice_ws, True)
            bob_state = _receive_room_state_with_ai(bob_ws, True)

            assert alice_state["payload"]["ai_enabled_by_default"] is True
            assert bob_state["payload"]["ai_enabled_by_default"] is True

            bob_ws.send_json(
                {
                    "type": "set_ai_enabled",
                    "request_id": "ai-2",
                    "payload": {"is_enabled": False},
                }
            )
            error = _receive_until(bob_ws, "action_error")
            assert error["payload"]["code"] == "NOT_HOST"


def test_websocket_player_can_use_time_card() -> None:
    client = TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )
    created = client.post(
        "/api/rooms",
        json={"nickname": "Alice", "small_blind": 5, "big_blind": 10},
    ).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]
    bob_id = client.post(
        f"/api/rooms/{room_code}/join",
        json={"nickname": "Bob"},
    ).json()["guest"]["guest_id"]

    client.post(f"/api/rooms/{room_code}/sit", json={"guest_id": alice_id, "seat_index": 0})
    client.post(f"/api/rooms/{room_code}/sit", json={"guest_id": bob_id, "seat_index": 1})
    client.post(f"/api/rooms/{room_code}/ready", json={"guest_id": alice_id, "is_ready": True})
    client.post(f"/api/rooms/{room_code}/ready", json={"guest_id": bob_id, "is_ready": True})
    client.post(f"/api/rooms/{room_code}/start", json={"guest_id": alice_id})

    with client.websocket_connect(f"/ws/rooms/{room_code}?guest_id={alice_id}") as websocket:
        initial = websocket.receive_json()
        assert initial["type"] == "room_state"
        assert initial["payload"]["viewer"]["can_act"] is True

        websocket.send_json(
            {
                "type": "use_time_card",
                "request_id": "time-card-1",
                "payload": {},
            }
        )
        state = _receive_until(websocket, "room_state")

        assert state["payload"]["seats"][0]["time_cards_remaining"] == 4
        assert any(event["type"] == "time_card_used" for event in state["payload"]["event_log"])


def _receive_until(websocket, message_type: str) -> dict:
    for _ in range(6):
        message = websocket.receive_json()
        if message["type"] == message_type:
            return message
    raise AssertionError(f"did not receive {message_type}")


def _receive_room_state_with_ai(websocket, expected: bool) -> dict:
    for _ in range(8):
        message = websocket.receive_json()
        if (
            message["type"] == "room_state"
            and message["payload"]["ai_enabled_by_default"] is expected
        ):
            return message
    raise AssertionError(f"did not receive room_state with ai={expected}")
