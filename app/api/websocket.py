from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.schemas.websocket import WebSocketMessage
from app.services.room_service import Room, RoomService, RoomServiceError
from app.services.websocket_manager import WebSocketManager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/rooms/{room_code}")
async def room_websocket(
    websocket: WebSocket,
    room_code: str,
    guest_id: str | None = None,
    nickname: str | None = None,
) -> None:
    await websocket.accept()
    room_service: RoomService = websocket.app.state.room_service
    websocket_manager: WebSocketManager = websocket.app.state.websocket_manager

    active_guest_id: str | None = None
    room: Room | None = None

    try:
        if guest_id and nickname:
            room, guest = room_service.join_room(
                room_code=room_code,
                guest_id=guest_id,
                nickname=nickname,
            )
            active_guest_id = guest.guest_id
            websocket_manager.connect(
                room_code=room.room_code,
                guest_id=active_guest_id,
                websocket=websocket,
            )
            await websocket_manager.broadcast_room_state(
                room=room,
                room_service=room_service,
            )
        elif guest_id:
            room, guest = room_service.reconnect(room_code=room_code, guest_id=guest_id)
            active_guest_id = guest.guest_id
            websocket_manager.connect(
                room_code=room.room_code,
                guest_id=active_guest_id,
                websocket=websocket,
            )
            await websocket_manager.broadcast_room_state(
                room=room,
                room_service=room_service,
            )
        else:
            await websocket.send_json(
                {
                    "type": "connected",
                    "payload": {"room_code": room_code.upper()},
                }
            )
    except RoomServiceError as exc:
        await websocket_manager.send_error(
            websocket,
            code=exc.code,
            message=exc.message,
        )
        await websocket.close(code=1008)
        return

    try:
        while True:
            raw_message = await websocket.receive_json()
            try:
                message = WebSocketMessage.model_validate(raw_message)
                room, active_guest_id = await _handle_message(
                    websocket=websocket,
                    websocket_manager=websocket_manager,
                    room_service=room_service,
                    room_code=room_code,
                    active_guest_id=active_guest_id,
                    message=message,
                )
                if room is not None and active_guest_id is not None:
                    await websocket_manager.broadcast_room_state(
                        room=room,
                        room_service=room_service,
                    )
            except ValidationError as exc:
                await websocket_manager.send_error(
                    websocket,
                    code="INVALID_MESSAGE",
                    message=str(exc),
                )
            except RoomServiceError as exc:
                await websocket_manager.send_error(
                    websocket,
                    code=exc.code,
                    message=exc.message,
                    request_id=raw_message.get("request_id")
                    if isinstance(raw_message, dict)
                    else None,
                )
            except (TypeError, ValueError) as exc:
                await websocket_manager.send_error(
                    websocket,
                    code="INVALID_PAYLOAD",
                    message=str(exc),
                    request_id=raw_message.get("request_id")
                    if isinstance(raw_message, dict)
                    else None,
                )
    except WebSocketDisconnect:
        websocket_manager.disconnect(
            room_code=room_code.upper(),
            guest_id=active_guest_id,
            websocket=websocket,
        )
        disconnected_room = room_service.disconnect(
            room_code=room_code,
            guest_id=active_guest_id,
        )
        if disconnected_room is not None:
            await websocket_manager.broadcast_room_state(
                room=disconnected_room,
                room_service=room_service,
            )


async def _handle_message(
    *,
    websocket: WebSocket,
    websocket_manager: WebSocketManager,
    room_service: RoomService,
    room_code: str,
    active_guest_id: str | None,
    message: WebSocketMessage,
) -> tuple[Room | None, str | None]:
    payload = message.payload

    if message.type == "heartbeat":
        timeout_room = room_service.process_timeouts(room_code=room_code)
        await websocket.send_json(
            {
                "type": "heartbeat_ack",
                "request_id": message.request_id,
                "payload": {},
            }
        )
        return timeout_room, active_guest_id

    if message.type == "join_room":
        requested_room_code = str(payload.get("room_code", room_code)).upper()
        if requested_room_code != room_code.upper():
            raise RoomServiceError("ROOM_MISMATCH", "WebSocket 已连接到其他房间")
        nickname = str(payload.get("nickname", "")).strip()
        if not nickname:
            raise RoomServiceError("NICKNAME_REQUIRED", "请输入昵称")
        payload_guest_id = _payload_guest_id(payload, active_guest_id)
        room, guest = room_service.join_room(
            room_code=room_code,
            nickname=nickname,
            guest_id=payload_guest_id,
        )
        if active_guest_id is None:
            websocket_manager.connect(
                room_code=room.room_code,
                guest_id=guest.guest_id,
                websocket=websocket,
            )
        return room, guest.guest_id

    guest_id = _require_active_guest_id(payload, active_guest_id)

    if message.type == "sit_down":
        return (
            room_service.sit_down(
                room_code=room_code,
                guest_id=guest_id,
                seat_index=_int_payload(payload, "seat_index", default=-1),
            ),
            guest_id,
        )
    if message.type == "stand_up":
        return room_service.stand_up(room_code=room_code, guest_id=guest_id), guest_id
    if message.type == "ready":
        return (
            room_service.set_ready(
                room_code=room_code,
                guest_id=guest_id,
                is_ready=_bool_payload(payload, "is_ready", default=True),
            ),
            guest_id,
        )
    if message.type == "start_game":
        return room_service.start_game(room_code=room_code, guest_id=guest_id), guest_id
    if message.type == "pause_game":
        return (
            room_service.set_paused(
                room_code=room_code,
                guest_id=guest_id,
                is_paused=_bool_payload(payload, "is_paused", default=True),
            ),
            guest_id,
        )
    if message.type == "end_game":
        return room_service.end_game(room_code=room_code, guest_id=guest_id), guest_id
    if message.type == "add_bot":
        return room_service.add_bot(room_code=room_code, guest_id=guest_id), guest_id
    if message.type in {"borrow_chips", "claim_training_chips"}:
        return (
            room_service.award_training_chips(
                room_code=room_code,
                guest_id=guest_id,
                amount=_int_payload(payload, "amount", default=5000),
            ),
            guest_id,
        )
    if message.type == "send_chat_message":
        room, chat_message = room_service.send_chat_message(
            room_code=room_code,
            guest_id=guest_id,
            content=str(payload.get("content", "")),
        )
        await websocket_manager.broadcast_chat_message(
            room=room,
            room_service=room_service,
            message=chat_message,
        )
        return room, guest_id
    if message.type == "set_ai_enabled":
        return (
            room_service.set_ai_enabled(
                room_code=room_code,
                guest_id=guest_id,
                is_enabled=_bool_payload(payload, "is_enabled", default=False),
            ),
            guest_id,
        )
    if message.type == "use_time_card":
        return room_service.use_time_card(room_code=room_code, guest_id=guest_id), guest_id
    if message.type == "player_action":
        return (
            room_service.player_action(
                room_code=room_code,
                guest_id=guest_id,
                action=str(payload.get("action", "")),
                amount=_int_payload(payload, "amount", default=0),
            ),
            guest_id,
        )
    if message.type == "leave_room":
        return room_service.leave_room(room_code=room_code, guest_id=guest_id), guest_id

    raise RoomServiceError("UNKNOWN_EVENT", f"未知 WebSocket 事件：{message.type}")


def _payload_guest_id(payload: dict, active_guest_id: str | None) -> str | None:
    value = payload.get("guest_id") or active_guest_id
    return str(value) if value else None


def _require_active_guest_id(payload: dict, active_guest_id: str | None) -> str:
    guest_id = _payload_guest_id(payload, active_guest_id)
    if guest_id is None:
        raise RoomServiceError("NOT_JOINED", "请先加入房间再操作")
    return guest_id


def _int_payload(payload: dict, key: str, *, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{key} 必须是整数")
    return int(value)


def _bool_payload(payload: dict, key: str, *, default: bool) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    raise ValueError(f"{key} 必须是布尔值")
