from __future__ import annotations

from random import Random

import pytest

from app.poker.deck import Deck, DeckExhaustedError


def test_standard_deck_has_52_unique_cards() -> None:
    deck = Deck.ordered()

    assert len(deck) == 52
    assert len(set(deck.cards)) == 52


def test_deal_and_burn_consume_cards() -> None:
    deck = Deck.ordered()

    first = deck.deal_one()
    burned = deck.burn()
    next_three = deck.deal(3)

    assert str(first) == "2s"
    assert str(burned) == "3s"
    assert [str(card) for card in next_three] == ["4s", "5s", "6s"]
    assert deck.remaining == 47


def test_cannot_deal_more_cards_than_remaining() -> None:
    deck = Deck.ordered()

    with pytest.raises(DeckExhaustedError):
        deck.deal(53)


def test_twenty_player_holdem_deal_has_enough_unique_cards() -> None:
    deck = Deck(rng=Random(20260608))

    hole_cards = []
    for _ in range(20):
        hole_cards.extend(deck.deal(2))

    burn_cards = [deck.burn()]
    community_cards = deck.deal(3)
    burn_cards.append(deck.burn())
    community_cards.extend(deck.deal(1))
    burn_cards.append(deck.burn())
    community_cards.extend(deck.deal(1))

    used_cards = hole_cards + burn_cards + community_cards

    assert len(hole_cards) == 40
    assert len(community_cards) == 5
    assert len(burn_cards) == 3
    assert len(used_cards) == 48
    assert len(set(used_cards)) == 48
    assert deck.remaining == 4
