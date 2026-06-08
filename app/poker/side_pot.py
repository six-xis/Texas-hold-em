from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class PlayerContribution:
    seat_index: int
    total_committed: int
    has_folded: bool = False


@dataclass(frozen=True, slots=True)
class SidePot:
    amount: int
    eligible_seat_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PotShare:
    seat_index: int
    amount: int


def calculate_side_pots(contributions: Iterable[PlayerContribution]) -> list[SidePot]:
    contribution_list = list(contributions)
    _validate_contributions(contribution_list)

    active_contributions = [
        contribution
        for contribution in contribution_list
        if contribution.total_committed > 0
    ]
    levels = sorted({contribution.total_committed for contribution in active_contributions})

    pots: list[SidePot] = []
    previous_level = 0
    for level in levels:
        participants = [
            contribution
            for contribution in active_contributions
            if contribution.total_committed >= level
        ]
        layer_amount = (level - previous_level) * len(participants)
        if layer_amount > 0:
            eligible = tuple(
                contribution.seat_index
                for contribution in participants
                if not contribution.has_folded
            )
            if eligible:
                pots.append(SidePot(amount=layer_amount, eligible_seat_indexes=eligible))
        previous_level = level

    return pots


def split_pot_amount(
    amount: int,
    winner_seat_indexes: Iterable[int],
    *,
    button_seat_index: int,
    max_seats: int = 20,
) -> tuple[PotShare, ...]:
    if amount < 0:
        raise ValueError("amount cannot be negative")

    winners = tuple(dict.fromkeys(winner_seat_indexes))
    if not winners:
        raise ValueError("At least one winner is required")
    if max_seats < 2:
        raise ValueError("max_seats must be at least 2")

    base_share = amount // len(winners)
    remainder = amount % len(winners)
    ordered_winners = sorted(
        winners,
        key=lambda seat_index: (seat_index - button_seat_index - 1) % max_seats,
    )

    shares_by_seat = {seat_index: base_share for seat_index in winners}
    for seat_index in ordered_winners[:remainder]:
        shares_by_seat[seat_index] += 1

    return tuple(PotShare(seat_index=seat_index, amount=shares_by_seat[seat_index]) for seat_index in winners)


def _validate_contributions(contributions: list[PlayerContribution]) -> None:
    seen_seats: set[int] = set()
    for contribution in contributions:
        if contribution.seat_index in seen_seats:
            raise ValueError(f"Duplicate seat contribution: {contribution.seat_index}")
        if contribution.total_committed < 0:
            raise ValueError("total_committed cannot be negative")
        seen_seats.add(contribution.seat_index)
