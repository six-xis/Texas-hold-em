from __future__ import annotations

from pydantic import BaseModel


class WinnerView(BaseModel):
    seat_index: int
    amount: int
    hand_category_name: str | None = None


class PotShareView(BaseModel):
    seat_index: int
    amount: int


class PotDistributionView(BaseModel):
    pot_index: int
    amount: int
    eligible_seat_indexes: list[int]
    winner_seat_indexes: list[int]
    shares: list[PotShareView]


class ShowdownHandView(BaseModel):
    seat_index: int
    category_name: str
    best_cards: list[str]


class HandResultView(BaseModel):
    winners: list[WinnerView]
    pot_distributions: list[PotDistributionView]
    showdown_hands: list[ShowdownHandView]
