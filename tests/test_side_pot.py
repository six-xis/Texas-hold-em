from __future__ import annotations

from app.poker.side_pot import (
    PlayerContribution,
    calculate_side_pots,
    split_pot_amount,
)


def test_calculates_main_pot_and_side_pot_from_commitments() -> None:
    pots = calculate_side_pots(
        [
            PlayerContribution(seat_index=0, total_committed=100),
            PlayerContribution(seat_index=1, total_committed=300),
            PlayerContribution(seat_index=2, total_committed=300),
        ]
    )

    assert [pot.amount for pot in pots] == [300, 400]
    assert [pot.eligible_seat_indexes for pot in pots] == [(0, 1, 2), (1, 2)]


def test_folded_players_contribute_but_are_not_eligible() -> None:
    pots = calculate_side_pots(
        [
            PlayerContribution(seat_index=0, total_committed=100),
            PlayerContribution(seat_index=1, total_committed=300, has_folded=True),
            PlayerContribution(seat_index=2, total_committed=300),
        ]
    )

    assert [pot.amount for pot in pots] == [300, 400]
    assert [pot.eligible_seat_indexes for pot in pots] == [(0, 2), (2,)]


def test_split_pot_handles_ties_and_odd_chip_by_button_order() -> None:
    shares = split_pot_amount(
        101,
        [0, 1],
        button_seat_index=0,
        max_seats=20,
    )

    assert {share.seat_index: share.amount for share in shares} == {0: 50, 1: 51}
