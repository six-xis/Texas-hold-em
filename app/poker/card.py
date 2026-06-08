from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum


class Suit(str, Enum):
    SPADES = "s"
    HEARTS = "h"
    DIAMONDS = "d"
    CLUBS = "c"

    @classmethod
    def from_symbol(cls, symbol: str) -> "Suit":
        normalized = symbol.lower()
        for suit in cls:
            if suit.value == normalized:
                return suit
        raise ValueError(f"Unknown suit symbol: {symbol!r}")


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    @property
    def symbol(self) -> str:
        return {
            Rank.TWO: "2",
            Rank.THREE: "3",
            Rank.FOUR: "4",
            Rank.FIVE: "5",
            Rank.SIX: "6",
            Rank.SEVEN: "7",
            Rank.EIGHT: "8",
            Rank.NINE: "9",
            Rank.TEN: "T",
            Rank.JACK: "J",
            Rank.QUEEN: "Q",
            Rank.KING: "K",
            Rank.ACE: "A",
        }[self]

    @classmethod
    def from_symbol(cls, symbol: str) -> "Rank":
        normalized = symbol.upper()
        if normalized == "10":
            normalized = "T"
        symbol_map = {rank.symbol: rank for rank in cls}
        try:
            return symbol_map[normalized]
        except KeyError as exc:
            raise ValueError(f"Unknown rank symbol: {symbol!r}") from exc


@dataclass(frozen=True, slots=True)
class Card:
    rank: Rank
    suit: Suit

    def __str__(self) -> str:
        return f"{self.rank.symbol}{self.suit.value}"

    def __repr__(self) -> str:
        return f"Card.parse({str(self)!r})"

    @classmethod
    def parse(cls, value: str) -> "Card":
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError(f"Invalid card: {value!r}")

        rank_symbol = normalized[:-1]
        suit_symbol = normalized[-1]
        return cls(
            rank=Rank.from_symbol(rank_symbol),
            suit=Suit.from_symbol(suit_symbol),
        )


def full_deck_cards() -> list[Card]:
    return [Card(rank=rank, suit=suit) for suit in Suit for rank in Rank]
