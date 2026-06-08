from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.schemas.room import (
    AddBotRequest,
    ChatMessageView,
    CreateRoomRequest,
    JoinRoomRequest,
    LeaveRoomRequest,
    PauseGameRequest,
    PlayerActionRequest,
    ReadyRequest,
    RoomEnvelope,
    RoomSummaryView,
    RoomStateView,
    SendChatMessageRequest,
    SitDownRequest,
    TimeCardRequest,
    TrainingChipsRequest,
)
from app.services.room_service import Room, RoomService, RoomServiceError
from app.services.websocket_manager import WebSocketManager

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=list[RoomSummaryView])
async def list_rooms(request: Request) -> list[RoomSummaryView]:
    return _room_service(request).list_rooms()


@router.post("", response_model=RoomEnvelope, status_code=status.HTTP_201_CREATED)
async def create_room(payload: CreateRoomRequest, request: Request) -> RoomEnvelope:
    service = _room_service(request)
    try:
        room, guest = service.create_room(
            nickname=payload.nickname,
            guest_id=payload.guest_id,
            small_blind=payload.small_blind,
            big_blind=payload.big_blind,
            ai_enabled_by_default=payload.ai_enabled_by_default,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.envelope_for(room, guest)


@router.post("/{room_code}/join", response_model=RoomEnvelope)
async def join_room(
    room_code: str,
    payload: JoinRoomRequest,
    request: Request,
) -> RoomEnvelope:
    service = _room_service(request)
    try:
        room, guest = service.join_room(
            room_code=room_code,
            nickname=payload.nickname,
            guest_id=payload.guest_id,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.envelope_for(room, guest)


@router.get("/{room_code}", response_model=RoomStateView)
async def get_room(
    room_code: str,
    request: Request,
    guest_id: str | None = None,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.get_room(room_code)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc
    return service.serialize_room(room, viewer_guest_id=guest_id)


@router.post("/{room_code}/leave", response_model=RoomStateView)
async def leave_room(
    room_code: str,
    payload: LeaveRoomRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.leave_room(room_code=room_code, guest_id=payload.guest_id)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/sit", response_model=RoomStateView)
async def sit_down(
    room_code: str,
    payload: SitDownRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.sit_down(
            room_code=room_code,
            guest_id=payload.guest_id,
            seat_index=payload.seat_index,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/stand", response_model=RoomStateView)
async def stand_up(
    room_code: str,
    payload: LeaveRoomRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.stand_up(room_code=room_code, guest_id=payload.guest_id)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/ready", response_model=RoomStateView)
async def set_ready(
    room_code: str,
    payload: ReadyRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.set_ready(
            room_code=room_code,
            guest_id=payload.guest_id,
            is_ready=payload.is_ready,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/start", response_model=RoomStateView)
async def start_game(
    room_code: str,
    payload: LeaveRoomRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.start_game(room_code=room_code, guest_id=payload.guest_id)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/pause", response_model=RoomStateView)
async def pause_game(
    room_code: str,
    payload: PauseGameRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.set_paused(
            room_code=room_code,
            guest_id=payload.guest_id,
            is_paused=payload.is_paused,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/end", response_model=RoomStateView)
async def end_game(
    room_code: str,
    payload: LeaveRoomRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.end_game(room_code=room_code, guest_id=payload.guest_id)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/bots", response_model=RoomStateView)
async def add_bot(
    room_code: str,
    payload: AddBotRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.add_bot(room_code=room_code, guest_id=payload.guest_id)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/borrow", response_model=RoomStateView)
async def borrow_chips(
    room_code: str,
    payload: TrainingChipsRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.award_training_chips(
            room_code=room_code,
            guest_id=payload.guest_id,
            amount=payload.amount,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/chat", response_model=ChatMessageView)
async def send_chat_message(
    room_code: str,
    payload: SendChatMessageRequest,
    request: Request,
) -> ChatMessageView:
    service = _room_service(request)
    try:
        room, message = service.send_chat_message(
            room_code=room_code,
            guest_id=payload.guest_id,
            content=payload.content,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    manager = _websocket_manager(request)
    await manager.broadcast_chat_message(room=room, room_service=service, message=message)
    await manager.broadcast_room_state(room=room, room_service=service)
    return service.serialize_chat_message(message)


@router.post("/{room_code}/action", response_model=RoomStateView)
async def player_action(
    room_code: str,
    payload: PlayerActionRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.player_action(
            room_code=room_code,
            guest_id=payload.guest_id,
            action=payload.action,
            amount=payload.amount,
        )
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


@router.post("/{room_code}/time-card", response_model=RoomStateView)
async def use_time_card(
    room_code: str,
    payload: TimeCardRequest,
    request: Request,
) -> RoomStateView:
    service = _room_service(request)
    try:
        room = service.use_time_card(room_code=room_code, guest_id=payload.guest_id)
    except RoomServiceError as exc:
        raise _http_error(exc) from exc

    await _broadcast(request, room)
    return service.serialize_room(room, viewer_guest_id=payload.guest_id)


def _room_service(request: Request) -> RoomService:
    return request.app.state.room_service


def _websocket_manager(request: Request) -> WebSocketManager:
    return request.app.state.websocket_manager


async def _broadcast(request: Request, room: Room) -> None:
    await _websocket_manager(request).broadcast_room_state(
        room=room,
        room_service=_room_service(request),
    )


def _http_error(exc: RoomServiceError) -> HTTPException:
    status_code = {
        "ROOM_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "ROOM_FULL": status.HTTP_409_CONFLICT,
        "SEAT_OCCUPIED": status.HTTP_409_CONFLICT,
        "NOT_HOST": status.HTTP_403_FORBIDDEN,
        "NOT_IN_ROOM": status.HTTP_403_FORBIDDEN,
        "NOT_SITTED": status.HTTP_400_BAD_REQUEST,
        "GAME_ALREADY_STARTED": status.HTTP_409_CONFLICT,
        "GAME_IN_PROGRESS": status.HTTP_409_CONFLICT,
        "GAME_NOT_RUNNING": status.HTTP_409_CONFLICT,
        "GAME_PAUSED": status.HTTP_409_CONFLICT,
        "HAND_IN_PROGRESS": status.HTTP_409_CONFLICT,
        "NOT_CURRENT_ACTOR": status.HTTP_409_CONFLICT,
        "NO_TIME_CARDS": status.HTTP_409_CONFLICT,
        "BORROW_NOT_ALLOWED": status.HTTP_409_CONFLICT,
        "TRAINING_CHIPS_NOT_ALLOWED": status.HTTP_409_CONFLICT,
        "NO_EMPTY_SEAT": status.HTTP_409_CONFLICT,
        "NOT_ALL_READY": status.HTTP_409_CONFLICT,
        "NOT_ENOUGH_PLAYERS": status.HTTP_400_BAD_REQUEST,
        "EMPTY_MESSAGE": status.HTTP_400_BAD_REQUEST,
        "MESSAGE_TOO_LONG": status.HTTP_400_BAD_REQUEST,
        "INVALID_BORROW_AMOUNT": status.HTTP_400_BAD_REQUEST,
        "INVALID_TRAINING_CHIPS_AMOUNT": status.HTTP_400_BAD_REQUEST,
        "INVALID_ACTION": status.HTTP_400_BAD_REQUEST,
        "INVALID_BLINDS": status.HTTP_400_BAD_REQUEST,
        "INVALID_SEAT": status.HTTP_400_BAD_REQUEST,
    }.get(exc.code, status.HTTP_400_BAD_REQUEST)
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.message},
    )
