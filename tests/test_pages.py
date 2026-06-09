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


def test_index_page_renders_lobby() -> None:
    client = make_client()

    response = client.get("/")

    assert response.status_code == 200
    assert "德州扑克" in response.text
    assert "创建房间" in response.text
    assert "注册昵称" in response.text
    assert "开启 AI 助手" in response.text
    assert "房主控制本房间 AI 助手" in response.text
    assert "ai-default" in response.text
    assert "最近房间" in response.text
    assert "/static/js/index.js" in response.text


def test_room_page_renders_game_shell() -> None:
    client = make_client()

    response = client.get("/rooms/abc123")

    assert response.status_code == 200
    assert "ABC123" in response.text
    assert "seat-grid" in response.text
    assert "event-log" in response.text
    assert "game-view" in response.text
    assert "AI助手" in response.text
    assert "下注金额" in response.text
    assert "聊天区" in response.text
    assert "净盈亏" in response.text
    assert "ranking-list" in response.text
    assert "showdown-modal" in response.text
    assert "card-animation-layer" in response.text
    assert "sound-volume" in response.text
    assert "扔鸡蛋" not in response.text
    assert "table-emote" not in response.text
    assert "领取 5000 训练筹码" in response.text
    assert "use-time-card" in response.text
    assert "时间卡 +30s" in response.text
    assert "table-player-pods" in response.text
    assert "添加智能机器人" in response.text
    assert "/static/js/room.js" in response.text


def test_static_assets_are_served() -> None:
    client = make_client()

    response = client.get("/static/js/room.js")

    assert response.status_code == 200
    assert "WebSocket" in response.text
    assert "soundManager" in response.text
    assert "SpeechSynthesisUtterance" in response.text
    assert "processRoomStateEffects" in response.text
    assert "set_ai_enabled" in response.text
    assert "use_time_card" in response.text
    assert "startHeartbeat" in response.text
    assert "speechSynthesis.cancel" in response.text
    assert "utterance.rate = 1.45" in response.text
    assert "send_table_emote" not in response.text
