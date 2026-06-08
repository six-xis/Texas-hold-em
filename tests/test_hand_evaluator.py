from __future__ import annotations

import pytest

from app.poker.card import Card
from app.poker.hand_evaluator import HandCategory, HandEvaluator


def make_cards(values: str) -> list[Card]:
    return [Card.parse(value) for value in values.split()]


@pytest.mark.parametrize(
    ("values", "category"),
    [
        ("As Kd Qh 8c 7s 4d 2h", HandCategory.HIGH_CARD),
        ("As Ad Kc Qs 9d 4c 2h", HandCategory.ONE_PAIR),
        ("Ah Ad Kc Ks 3d 8s 2c", HandCategory.TWO_PAIR),
        ("Ah Ad Ac Ks Qd 7c 2h", HandCategory.THREE_OF_A_KIND),
        ("As Kd Qh Jc Ts 3d 2c", HandCategory.STRAIGHT),
        ("Ah Qh 9h 5h 2h Kd 3s", HandCategory.FLUSH),
        ("Th Td Tc 9s 9d 2c 3h", HandCategory.FULL_HOUSE),
        ("Ah Ad Ac As Kd 2c 3h", HandCategory.FOUR_OF_A_KIND),
        ("9c 8c 7c 6c 5c Ah Kd", HandCategory.STRAIGHT_FLUSH),
        ("As Ks Qs Js Ts 2d 3h", HandCategory.ROYAL_FLUSH),
    ],
)
def test_evaluates_all_hand_categories(values: str, category: HandCategory) -> None:
    evaluation = HandEvaluator.evaluate(make_cards(values))

    assert evaluation.category == category


def test_a2345_is_lowest_straight() -> None:
    evaluation = HandEvaluator.evaluate(make_cards("As 2d 3h 4c 5s 9d Kh"))

    assert evaluation.category == HandCategory.STRAIGHT
    assert evaluation.ranks == (5,)


def test_akqjt_is_highest_non_flush_straight() -> None:
    evaluation = HandEvaluator.evaluate(make_cards("As Kd Qh Jc Ts 2d 3h"))

    assert evaluation.category == HandCategory.STRAIGHT
    assert evaluation.ranks == (14,)


def test_same_pair_compares_kickers() -> None:
    left = make_cards("Ah Ad Kc Qs 9d 4c 2h")
    right = make_cards("As Ac Kh Js 9c 4d 2c")

    assert HandEvaluator.compare(left, right) == 1


def test_two_pair_compares_high_pair_then_low_pair_then_kicker() -> None:
    better_low_pair = make_cards("Ah Ad Kc Ks 3d 8s 2c")
    worse_low_pair = make_cards("As Ac Qh Qd Kd 8h 2s")
    better_kicker = make_cards("Ah Ad Kc Ks 5d 3s 2c")
    worse_kicker = make_cards("As Ac Kh Kd 4c 3h 2s")

    assert HandEvaluator.compare(better_low_pair, worse_low_pair) == 1
    assert HandEvaluator.compare(better_kicker, worse_kicker) == 1


def test_full_house_compares_trips_then_pair() -> None:
    better_trips = make_cards("Th Td Tc 9s 9d 2c 3h")
    worse_trips = make_cards("9h 9c 9d As Ad 2h 3s")
    better_pair = make_cards("Th Td Tc As Ad 2c 3h")
    worse_pair = make_cards("Ts Tc Th Ks Kd 2h 3s")

    assert HandEvaluator.compare(better_trips, worse_trips) == 1
    assert HandEvaluator.compare(better_pair, worse_pair) == 1


def test_flush_compares_each_card_descending() -> None:
    queen_second_card = make_cards("Ah Qh 9h 5h 2h Kd 3s")
    jack_second_card = make_cards("As Js Ts 8s 7s Kc 3d")

    assert HandEvaluator.compare(queen_second_card, jack_second_card) == 1


def test_multiple_players_can_tie_for_best_hand() -> None:
    winners = HandEvaluator.winners(
        {
            "alice": make_cards("As Kd Qh Jc Ts 2d 3h"),
            "bob": make_cards("Ac Kh Qs Jh Td 4d 5c"),
            "carol": make_cards("9s 9d Ah Kc Qd 3h 2c"),
        }
    )

    assert winners == ["alice", "bob"]


def test_rejects_duplicate_cards() -> None:
    with pytest.raises(ValueError, match="Duplicate cards"):
        HandEvaluator.evaluate(make_cards("As As Kd Qh Jc Ts 2d"))
