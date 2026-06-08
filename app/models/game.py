from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GameHand(Base):
    __tablename__ = "game_hands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    room_id: Mapped[str] = mapped_column(ForeignKey("rooms.id"), index=True)
    hand_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="preflop")
    button_seat_index: Mapped[int] = mapped_column(Integer)
    small_blind_seat_index: Mapped[int] = mapped_column(Integer)
    big_blind_seat_index: Mapped[int] = mapped_column(Integer)
    community_cards_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    burn_cards_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    pot_total: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GameHandPlayer(Base):
    __tablename__ = "game_hand_players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    hand_id: Mapped[str] = mapped_column(ForeignKey("game_hands.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("guest_users.id"), index=True)
    seat_index: Mapped[int] = mapped_column(Integer)
    starting_chips: Mapped[int] = mapped_column(Integer)
    ending_chips: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hole_cards_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_folded: Mapped[bool] = mapped_column(Boolean, default=False)
    is_all_in: Mapped[bool] = mapped_column(Boolean, default=False)
    total_committed: Mapped[int] = mapped_column(Integer, default=0)
    final_rank_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    final_best_cards_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)


class GameActionLog(Base):
    __tablename__ = "game_action_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    hand_id: Mapped[str] = mapped_column(ForeignKey("game_hands.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("guest_users.id"), index=True)
    seat_index: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(24))
    action_type: Mapped[str] = mapped_column(String(24))
    amount: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
