from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from app.services.room_service import ChatMessage, Room, RoomService


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, dict[str, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )

    def connect(self, *, room_code: str, guest_id: str, websocket: WebSocket) -> None:
        self._connections[room_code][guest_id].add(websocket)

    def disconnect(self, *, room_code: str, guest_id: str | None, websocket: WebSocket) -> None:
        if guest_id is None:
            return
        room_connections = self._connections.get(room_code)
        if room_connections is None:
            return

        sockets = room_connections.get(guest_id)
        if sockets is None:
            return

        sockets.discard(websocket)
        if not sockets:
            del room_connections[guest_id]
        if not room_connections:
            del self._connections[room_code]

    async def send_error(
        self,
        websocket: WebSocket,
        *,
        code: str,
        message: str,
        request_id: str | None = None,
    ) -> None:
        await websocket.send_json(
            {
                "type": "action_error",
                "request_id": request_id,
                "payload": {"code": code, "message": message},
            }
        )

    async def broadcast_room_state(self, *, room: Room, room_service: RoomService) -> None:
        room_connections = self._connections.get(room.room_code, {})
        stale_connections: list[tuple[str, WebSocket]] = []

        for guest_id, sockets in list(room_connections.items()):
            state = room_service.serialize_room(room, viewer_guest_id=guest_id)
            payload = {
                "type": "room_state",
                "revision": room.revision,
                "payload": state.model_dump(mode="json"),
            }
            for websocket in list(sockets):
                try:
                    await websocket.send_json(payload)
                except RuntimeError:
                    stale_connections.append((guest_id, websocket))

        for guest_id, websocket in stale_connections:
            self.disconnect(
                room_code=room.room_code,
                guest_id=guest_id,
                websocket=websocket,
            )

    async def broadcast_chat_message(
        self,
        *,
        room: Room,
        room_service: RoomService,
        message: ChatMessage,
    ) -> None:
        room_connections = self._connections.get(room.room_code, {})
        stale_connections: list[tuple[str, WebSocket]] = []
        payload = {
            "type": "chat_message",
            "payload": room_service.serialize_chat_message(message).model_dump(mode="json"),
        }

        for guest_id, sockets in list(room_connections.items()):
            for websocket in list(sockets):
                try:
                    await websocket.send_json(payload)
                except RuntimeError:
                    stale_connections.append((guest_id, websocket))

        for guest_id, websocket in stale_connections:
            self.disconnect(
                room_code=room.room_code,
                guest_id=guest_id,
                websocket=websocket,
            )
