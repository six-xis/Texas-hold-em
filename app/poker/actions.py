from __future__ import annotations

from dataclasses import dataclass

from app.poker.enums import PlayerActionType


@dataclass(frozen=True, slots=True)
class PlayerAction:
    action_type: PlayerActionType
    amount: int = 0

    @classmethod
    def fold(cls) -> "PlayerAction":
        return cls(PlayerActionType.FOLD)

    @classmethod
    def check(cls) -> "PlayerAction":
        return cls(PlayerActionType.CHECK)

    @classmethod
    def call(cls) -> "PlayerAction":
        return cls(PlayerActionType.CALL)

    @classmethod
    def bet(cls, amount: int) -> "PlayerAction":
        return cls(PlayerActionType.BET, amount)

    @classmethod
    def raise_to(cls, amount: int) -> "PlayerAction":
        return cls(PlayerActionType.RAISE, amount)

    @classmethod
    def all_in(cls) -> "PlayerAction":
        return cls(PlayerActionType.ALL_IN)
