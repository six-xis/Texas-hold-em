from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes import router as room_router
from app.api.websocket import router as websocket_router
from app.config import settings
from app.database import init_db_with_retries
from app.services.room_service import RoomService
from app.services.websocket_manager import WebSocketManager

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.init_db:
        init_db_with_retries()

    cleanup_task: asyncio.Task[None] | None = None
    if settings.daily_room_cleanup_enabled:
        cleanup_task = asyncio.create_task(_daily_room_cleanup_loop(app))

    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task


async def _daily_room_cleanup_loop(app: FastAPI) -> None:
    timezone = _cleanup_timezone()
    while True:
        now = datetime.now(timezone)
        next_midnight = datetime.combine(
            (now + timedelta(days=1)).date(),
            time.min,
            tzinfo=timezone,
        )
        await asyncio.sleep(max(1.0, (next_midnight - now).total_seconds()))

        target_date = (datetime.now(timezone) - timedelta(microseconds=1)).date()
        removed_rooms = app.state.room_service.clear_rooms_created_on(
            target_date,
            timezone=timezone,
        )
        for room in removed_rooms:
            await app.state.websocket_manager.broadcast_room_closed(
                room_code=room.room_code,
                message="每日 00:00 自动清理今日房间，已返回大厅。",
            )


def _cleanup_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.daily_room_cleanup_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def create_app(
    *,
    room_service: RoomService | None = None,
    websocket_manager: WebSocketManager | None = None,
) -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.room_service = room_service or RoomService()
    app.state.websocket_manager = websocket_manager or WebSocketManager()

    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    app.include_router(room_router, prefix="/api")
    app.include_router(websocket_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "index.html")

    @app.get("/rooms/{room_code}", response_class=HTMLResponse)
    async def room_page(request: Request, room_code: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "room.html",
            {"room_code": room_code.upper()},
        )

    return app


app = create_app()
