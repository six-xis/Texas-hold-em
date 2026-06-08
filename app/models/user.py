from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GuestUser(Base):
    __tablename__ = "guest_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    guest_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(24))
    chips: Mapped[int] = mapped_column(Integer, default=10_000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
