from __future__ import annotations

import random
from collections.abc import Iterable
from random import Random

from app.poker.card import Card, full_deck_cards


class DeckExhaustedError(RuntimeError):
    pass


class Deck:
    def __init__(
        self,
        cards: Iterable[Card] | None = None,
        *,
        shuffle: bool = True,
        rng: Random | None = None,
    ) -> None:
        self._cards = list(cards) if cards is not None else full_deck_cards()
        if shuffle:
            self.shuffle(rng=rng)

    @classmethod
    def ordered(cls) -> "Deck":
        return cls(shuffle=False)

    @property
    def cards(self) -> tuple[Card, ...]:
        return tuple(self._cards)

    @property
    def remaining(self) -> int:
        return len(self._cards)

    def __len__(self) -> int:
        return self.remaining

    def shuffle(self, rng: Random | None = None) -> None:
        randomizer = rng or random
        randomizer.shuffle(self._cards)

    def deal(self, count: int = 1) -> list[Card]:
        if count < 1:
            raise ValueError("count must be at least 1")
        if count > self.remaining:
            raise DeckExhaustedError(
                f"Cannot deal {count} cards from deck with {self.remaining} remaining"
            )

        dealt = self._cards[:count]
        del self._cards[:count]
        return dealt

    def deal_one(self) -> Card:
        return self.deal(1)[0]

    def burn(self) -> Card:
        return self.deal_one()
