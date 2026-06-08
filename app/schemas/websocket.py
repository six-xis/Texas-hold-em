from __future__ import annotations

from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    type: str
    request_id: str | None = None
    payload: dict = Field(default_factory=dict)


class WebSocketErrorPayload(BaseModel):
    code: str
    message: str


class WebSocketEnvelope(BaseModel):
    type: str
    revision: int | None = None
    request_id: str | None = None
    payload: dict
