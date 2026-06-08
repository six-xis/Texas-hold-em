from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from functools import total_ordering
from itertools import combinations

from app.poker.card import Card


class HandCategory(IntEnum):
    HIGH_CARD = 1
    ONE_PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10

    @property
    def label(self) -> str:
        return {
            HandCategory.HIGH_CARD: "High Card",
            HandCategory.ONE_PAIR: "One Pair",
            HandCategory.TWO_PAIR: "Two Pair",
            HandCategory.THREE_OF_A_KIND: "Three of a Kind",
            HandCategory.STRAIGHT: "Straight",
            HandCategory.FLUSH: "Flush",
            HandCategory.FULL_HOUSE: "Full House",
            HandCategory.FOUR_OF_A_KIND: "Four of a Kind",
            HandCategory.STRAIGHT_FLUSH: "Straight Flush",
            HandCategory.ROYAL_FLUSH: "Royal Flush",
        }[self]


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class HandEvaluation:
    category: HandCategory
    ranks: tuple[int, ...]
    cards: tuple[Card, ...]

    @property
    def strength(self) -> tuple[int, tuple[int, ...]]:
        return int(self.category), self.ranks

    @property
    def category_name(self) -> str:
        return self.category.label

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, HandEvaluation):
            return NotImplemented
        return self.strength < other.strength

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, HandEvaluation):
            return NotImplemented
        return self.strength == other.strength

    def __hash__(self) -> int:
        return hash(self.strength)


class HandEvaluator:
    @staticmethod
    def evaluate(cards: Sequence[Card]) -> HandEvaluation:
        if len(cards) < 5:
            raise ValueError("At least 5 cards are required")
        if len(cards) > 7:
            raise ValueError("At most 7 cards can be evaluated")
        if len(set(cards)) != len(cards):
            raise ValueError("Duplicate cards cannot be evaluated")

        best: HandEvaluation | None = None
        for five_cards in combinations(cards, 5):
            evaluation = _evaluate_five(tuple(five_cards))
            if best is None or evaluation > best:
                best = evaluation

        if best is None:
            raise RuntimeError("No hand evaluation was produced")
        return best

    @staticmethod
    def compare(left: Sequence[Card], right: Sequence[Card]) -> int:
        left_eval = HandEvaluator.evaluate(left)
        right_eval = HandEvaluator.evaluate(right)
        if left_eval > right_eval:
            return 1
        if left_eval < right_eval:
            return -1
        return 0

    @staticmethod
    def winners(hands: Mapping[str, Sequence[Card]]) -> list[str]:
        if not hands:
            raise ValueError("At least one hand is required")

        evaluations = {
            player_id: HandEvaluator.evaluate(cards)
            for player_id, cards in hands.items()
        }
        best = max(evaluations.values())
        return [
            player_id
            for player_id, evaluation in evaluations.items()
            if evaluation == best
        ]


def _evaluate_five(cards: tuple[Card, ...]) -> HandEvaluation:
    ranks = [int(card.rank) for card in cards]
    rank_counts = Counter(ranks)
    straight_high = _straight_high(ranks)
    is_flush = len({card.suit for card in cards}) == 1

    if is_flush and straight_high is not None:
        category = (
            HandCategory.ROYAL_FLUSH
            if straight_high == 14 and set(ranks) == {10, 11, 12, 13, 14}
            else HandCategory.STRAIGHT_FLUSH
        )
        return HandEvaluation(
            category=category,
            ranks=(straight_high,),
            cards=_order_cards(cards, category, (straight_high,)),
        )

    four_ranks = _ranks_with_count(rank_counts, 4)
    if four_ranks:
        quad_rank = four_ranks[0]
        kicker = max(rank for rank in ranks if rank != quad_rank)
        category = HandCategory.FOUR_OF_A_KIND
        return HandEvaluation(
            category=category,
            ranks=(quad_rank, kicker),
            cards=_order_cards(cards, category, (quad_rank, kicker)),
        )

    triple_ranks = _ranks_with_count(rank_counts, 3)
    pair_ranks = _ranks_with_count(rank_counts, 2)
    if triple_ranks and pair_ranks:
        category = HandCategory.FULL_HOUSE
        return HandEvaluation(
            category=category,
            ranks=(triple_ranks[0], pair_ranks[0]),
            cards=_order_cards(cards, category, (triple_ranks[0], pair_ranks[0])),
        )

    if is_flush:
        category = HandCategory.FLUSH
        flush_ranks = tuple(sorted(ranks, reverse=True))
        return HandEvaluation(
            category=category,
            ranks=flush_ranks,
            cards=_order_cards(cards, category, flush_ranks),
        )

    if straight_high is not None:
        category = HandCategory.STRAIGHT
        return HandEvaluation(
            category=category,
            ranks=(straight_high,),
            cards=_order_cards(cards, category, (straight_high,)),
        )

    if triple_ranks:
        trips_rank = triple_ranks[0]
        kickers = tuple(
            sorted((rank for rank in ranks if rank != trips_rank), reverse=True)[:2]
        )
        category = HandCategory.THREE_OF_A_KIND
        return HandEvaluation(
            category=category,
            ranks=(trips_rank, *kickers),
            cards=_order_cards(cards, category, (trips_rank, *kickers)),
        )

    if len(pair_ranks) >= 2:
        high_pair, low_pair = pair_ranks[:2]
        kicker = max(rank for rank in ranks if rank not in {high_pair, low_pair})
        category = HandCategory.TWO_PAIR
        return HandEvaluation(
            category=category,
            ranks=(high_pair, low_pair, kicker),
            cards=_order_cards(cards, category, (high_pair, low_pair, kicker)),
        )

    if len(pair_ranks) == 1:
        pair_rank = pair_ranks[0]
        kickers = tuple(
            sorted((rank for rank in ranks if rank != pair_rank), reverse=True)[:3]
        )
        category = HandCategory.ONE_PAIR
        return HandEvaluation(
            category=category,
            ranks=(pair_rank, *kickers),
            cards=_order_cards(cards, category, (pair_rank, *kickers)),
        )

    category = HandCategory.HIGH_CARD
    high_cards = tuple(sorted(ranks, reverse=True))
    return HandEvaluation(
        category=category,
        ranks=high_cards,
        cards=_order_cards(cards, category, high_cards),
    )


def _ranks_with_count(rank_counts: Counter[int], count: int) -> list[int]:
    return sorted(
        (rank for rank, rank_count in rank_counts.items() if rank_count == count),
        reverse=True,
    )


def _straight_high(ranks: Sequence[int]) -> int | None:
    unique_ranks = set(ranks)
    if {14, 5, 4, 3, 2}.issubset(unique_ranks):
        return 5

    for high in range(14, 5 - 1, -1):
        sequence = set(range(high - 4, high + 1))
        if sequence.issubset(unique_ranks):
            return high
    return None


def _order_cards(
    cards: tuple[Card, ...],
    category: HandCategory,
    ranks: tuple[int, ...],
) -> tuple[Card, ...]:
    if category in {
        HandCategory.STRAIGHT,
        HandCategory.STRAIGHT_FLUSH,
        HandCategory.ROYAL_FLUSH,
    }:
        high = ranks[0]
        rank_order = [5, 4, 3, 2, 14] if high == 5 else list(range(high, high - 5, -1))
        return tuple(_pick_cards_by_rank(cards, rank_order))

    ordered_cards: list[Card] = []
    remaining = list(cards)
    for rank in ranks:
        matching = sorted(
            (card for card in remaining if int(card.rank) == rank),
            key=lambda card: card.suit.value,
        )
        ordered_cards.extend(matching)
        remaining = [card for card in remaining if int(card.rank) != rank]

    if remaining:
        ordered_cards.extend(
            sorted(remaining, key=lambda card: (int(card.rank), card.suit.value), reverse=True)
        )
    return tuple(ordered_cards)


def _pick_cards_by_rank(cards: tuple[Card, ...], ranks: Sequence[int]) -> list[Card]:
    picked: list[Card] = []
    available = list(cards)
    for rank in ranks:
        for index, card in enumerate(available):
            if int(card.rank) == rank:
                picked.append(card)
                del available[index]
                break
    return picked
