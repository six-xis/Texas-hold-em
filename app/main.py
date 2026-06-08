from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from collections.abc import AsyncIterator

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
    yield


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
