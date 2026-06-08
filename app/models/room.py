from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    room_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    host_user_id: Mapped[str] = mapped_column(ForeignKey("guest_users.id"))
    status: Mapped[str] = mapped_column(String(24), default="waiting")
    small_blind: Mapped[int] = mapped_column(Integer, default=50)
    big_blind: Mapped[int] = mapped_column(Integer, default=100)
    ai_enabled_by_default: Mapped[bool] = mapped_column(Boolean, default=False)
    max_seats: Mapped[int] = mapped_column(Integer, default=20)
    button_seat_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_hand_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class RoomMember(Base):
    __tablename__ = "room_members"
    __table_args__ = (UniqueConstraint("room_id", "user_id", name="uq_room_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("guest_users.id"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="player")
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RoomSeat(Base):
    __tablename__ = "room_seats"
    __table_args__ = (UniqueConstraint("room_id", "seat_index", name="uq_room_seat"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    seat_index: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("guest_users.id"), nullable=True)
    is_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
