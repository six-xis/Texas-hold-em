from __future__ import annotations

import app.models  # noqa: F401
from app.database import Base


def test_sqlalchemy_models_are_registered() -> None:
    table_names = set(Base.metadata.tables)

    assert {
        "guest_users",
        "rooms",
        "room_members",
        "room_seats",
        "game_hands",
        "game_hand_players",
        "game_action_logs",
    }.issubset(table_names)
    assert "ai_enabled_by_default" in Base.metadata.tables["rooms"].columns
