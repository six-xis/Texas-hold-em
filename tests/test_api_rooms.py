from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.room_service import RoomService
from app.services.websocket_manager import WebSocketManager


def make_client() -> TestClient:
    return TestClient(
        create_app(
            room_service=RoomService(),
            websocket_manager=WebSocketManager(),
        )
    )


def test_http_room_lifecycle() -> None:
    client = make_client()

    create_response = client.post(
        "/api/rooms",
        json={"nickname": "Alice", "small_blind": 5, "big_blind": 10},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]
    assert created["room"]["ai_enabled_by_default"] is False

    join_response = client.post(
        f"/api/rooms/{room_code}/join",
        json={"nickname": "Bob"},
    )
    assert join_response.status_code == 200
    bob_id = join_response.json()["guest"]["guest_id"]

    assert client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": alice_id, "seat_index": 0},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": bob_id, "seat_index": 1},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/ready",
        json={"guest_id": alice_id, "is_ready": True},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/ready",
        json={"guest_id": bob_id, "is_ready": True},
    ).status_code == 200

    start_response = client.post(
        f"/api/rooms/{room_code}/start",
        json={"guest_id": alice_id},
    )

    assert start_response.status_code == 200
    state = start_response.json()
    assert state["status"] == "playing"
    assert state["phase"] == "preflop"
    assert state["viewer"]["can_act"] is True
    assert state["hand_number"] == 1
    assert state["player_count"] == 2
    assert state["action_options"]["to_call"] == 5
    assert state["action_options"]["min_raise_to"] == 20
    assert state["ai_assistant"]["enabled"] is False
    assert state["seats"][0]["position_label"] == "BTN/SB"
    assert state["seats"][1]["position_label"] == "BB"
    assert len(state["seats"][0]["hole_cards"]) == 2
    assert state["seats"][1]["hole_cards"] == ["hidden", "hidden"]
    assert state["rankings"][0]["buy_in_chips"] == 10000


def test_http_register_rejects_duplicate_nickname_and_can_create_room() -> None:
    client = make_client()

    register_response = client.post("/api/rooms/register", json={"nickname": "Alice"})

    assert register_response.status_code == 201
    registered = register_response.json()
    assert registered["nickname"] == "Alice"
    assert registered["guest_id"]

    duplicate_response = client.post("/api/rooms/register", json={"nickname": "alice"})
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"]["code"] == "USER_ALREADY_EXISTS"

    reserved_name_response = client.post("/api/rooms", json={"nickname": "Alice"})
    assert reserved_name_response.status_code == 409

    create_response = client.post(
        "/api/rooms",
        json={"nickname": "ignored", "guest_id": registered["guest_id"]},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["guest"]["nickname"] == "Alice"
    assert created["room"]["rankings"][0]["nickname"] == "Alice"


def test_http_room_can_enable_ai_assistant_by_default() -> None:
    client = make_client()

    create_response = client.post(
        "/api/rooms",
        json={
            "nickname": "Alice",
            "small_blind": 5,
            "big_blind": 10,
            "ai_enabled_by_default": True,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    room_code = created["room"]["room_code"]
    assert created["room"]["ai_enabled_by_default"] is True

    fetched = client.get(f"/api/rooms/{room_code}")
    assert fetched.status_code == 200
    assert fetched.json()["ai_enabled_by_default"] is True

    rooms = client.get("/api/rooms").json()
    assert rooms[0]["room_code"] == room_code
    assert rooms[0]["ai_enabled_by_default"] is True


def test_http_rejects_occupied_seat() -> None:
    client = make_client()
    created = client.post("/api/rooms", json={"nickname": "Alice"}).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]
    bob_id = client.post(
        f"/api/rooms/{room_code}/join",
        json={"nickname": "Bob"},
    ).json()["guest"]["guest_id"]

    first = client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": alice_id, "seat_index": 0},
    )
    second = client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": bob_id, "seat_index": 0},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "SEAT_OCCUPIED"


def test_http_lists_recent_rooms() -> None:
    client = make_client()
    created = client.post("/api/rooms", json={"nickname": "Alice"}).json()

    response = client.get("/api/rooms")

    assert response.status_code == 200
    rooms = response.json()
    assert rooms[0]["room_code"] == created["room"]["room_code"]
    assert rooms[0]["host_nickname"] == "Alice"
    assert rooms[0]["can_join"] is True


def test_http_host_can_add_bot() -> None:
    client = make_client()
    created = client.post("/api/rooms", json={"nickname": "Alice"}).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]

    response = client.post(
        f"/api/rooms/{room_code}/bots",
        json={"guest_id": alice_id},
    )

    assert response.status_code == 200
    state = response.json()
    bot_seats = [seat for seat in state["seats"] if seat["is_bot"]]
    assert len(bot_seats) == 1
    assert bot_seats[0]["occupied"] is True
    assert bot_seats[0]["is_ready"] is True
    assert bot_seats[0]["nickname"].startswith("智能机器人")


def test_http_host_can_pause_resume_and_end_game() -> None:
    client = make_client()

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

    assert client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": alice_id, "seat_index": 0},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": bob_id, "seat_index": 1},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/ready",
        json={"guest_id": alice_id, "is_ready": True},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/ready",
        json={"guest_id": bob_id, "is_ready": True},
    ).status_code == 200
    assert client.post(
        f"/api/rooms/{room_code}/start",
        json={"guest_id": alice_id},
    ).status_code == 200

    pause_response = client.post(
        f"/api/rooms/{room_code}/pause",
        json={"guest_id": alice_id, "is_paused": True},
    )
    assert pause_response.status_code == 200
    paused = pause_response.json()
    assert paused["is_paused"] is True
    assert paused["viewer"]["can_act"] is False
    assert paused["action_expires_at"] is None

    rejected_action = client.post(
        f"/api/rooms/{room_code}/action",
        json={"guest_id": alice_id, "action": "call", "amount": 0},
    )
    assert rejected_action.status_code == 409
    assert rejected_action.json()["detail"]["code"] == "GAME_PAUSED"

    resume_response = client.post(
        f"/api/rooms/{room_code}/pause",
        json={"guest_id": alice_id, "is_paused": False},
    )
    assert resume_response.status_code == 200
    resumed = resume_response.json()
    assert resumed["is_paused"] is False
    assert resumed["viewer"]["can_act"] is True
    assert resumed["action_expires_at"] is not None

    end_response = client.post(
        f"/api/rooms/{room_code}/end",
        json={"guest_id": alice_id},
    )
    assert end_response.status_code == 200
    ended = end_response.json()
    assert ended["status"] == "waiting"
    assert ended["phase"] == "waiting"
    assert ended["is_paused"] is False
    assert ended["pot_total"] == 0


def test_http_training_chips_and_chat_endpoints() -> None:
    client = make_client()
    created = client.post("/api/rooms", json={"nickname": "Alice"}).json()
    room_code = created["room"]["room_code"]
    alice_id = created["guest"]["guest_id"]

    client.post(
        f"/api/rooms/{room_code}/sit",
        json={"guest_id": alice_id, "seat_index": 0},
    )
    rejected = client.post(
        f"/api/rooms/{room_code}/borrow",
        json={"guest_id": alice_id, "amount": 5000},
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["code"] == "TRAINING_CHIPS_NOT_ALLOWED"

    service = client.app.state.room_service
    room = service.get_room(room_code)
    room.members[alice_id].chips = 0

    borrowed = client.post(
        f"/api/rooms/{room_code}/borrow",
        json={"guest_id": alice_id, "amount": 5000},
    )
    assert borrowed.status_code == 200
    borrowed_state = borrowed.json()
    assert borrowed_state["seats"][0]["chips"] == 5000
    assert borrowed_state["seats"][0]["training_chips_awarded"] == 5000

    chat = client.post(
        f"/api/rooms/{room_code}/chat",
        json={"guest_id": alice_id, "content": "  你好  "},
    )
    assert chat.status_code == 200
    assert chat.json()["content"] == "你好"

    state = client.get(f"/api/rooms/{room_code}", params={"guest_id": alice_id}).json()
    assert state["chat_messages"][-1]["content"] == "你好"
