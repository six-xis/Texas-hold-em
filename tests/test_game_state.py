from __future__ import annotations

import pytest

from app.poker.card import Card
from app.poker.deck import Deck
from app.poker.enums import BettingPhase, PlayerActionType
from app.poker.game_state import GameState, InvalidGameAction, PlayerProfile


def make_cards(values: str) -> list[Card]:
    return [Card.parse(value) for value in values.split()]


def scripted_deck(values: str) -> Deck:
    return Deck(make_cards(values), shuffle=False)


def players(*chips: int) -> list[PlayerProfile]:
    return [
        PlayerProfile(
            seat_index=seat_index,
            player_id=f"player-{seat_index}",
            nickname=f"P{seat_index}",
            chips=chip_count,
        )
        for seat_index, chip_count in enumerate(chips)
    ]


def chips_by_seat(state: GameState) -> dict[int, int]:
    return {seat.seat_index: seat.chips for seat in state.seats}


def test_heads_up_call_and_check_advances_from_preflop_to_flop() -> None:
    state = GameState.start_new_hand(
        players(1000, 1000),
        button_seat_index=0,
        small_blind=5,
        big_blind=10,
        deck=Deck.ordered(),
    )

    assert state.small_blind_seat_index == 0
    assert state.big_blind_seat_index == 1
    assert state.current_actor_seat_index == 0
    assert state.current_bet == 10

    state.apply_action(0, PlayerActionType.CALL)
    assert state.current_actor_seat_index == 1

    state.apply_action(1, PlayerActionType.CHECK)

    assert state.phase == BettingPhase.FLOP
    assert len(state.community_cards) == 3
    assert len(state.burn_cards) == 1
    assert state.current_actor_seat_index == 1
    assert state.current_bet == 0
    assert [seat.current_bet for seat in state.seats] == [0, 0]
    assert state.pot_total == 20


def test_fold_awards_pot_immediately_to_last_active_player() -> None:
    state = GameState.start_new_hand(
        players(100, 100),
        button_seat_index=0,
        small_blind=5,
        big_blind=10,
        deck=Deck.ordered(),
    )

    state.apply_action(0, PlayerActionType.FOLD)

    assert state.phase == BettingPhase.FINISHED
    assert state.current_actor_seat_index is None
    assert chips_by_seat(state) == {0: 95, 1: 105}
    assert state.result is not None
    assert state.result.winners[0].seat_index == 1
    assert state.result.winners[0].amount == 15


def test_rejects_actions_from_wrong_seat_and_illegal_check() -> None:
    state = GameState.start_new_hand(
        players(1000, 1000),
        button_seat_index=0,
        small_blind=5,
        big_blind=10,
        deck=Deck.ordered(),
    )

    with pytest.raises(InvalidGameAction, match="not this seat"):
        state.apply_action(1, PlayerActionType.CHECK)

    with pytest.raises(InvalidGameAction, match="Cannot check"):
        state.apply_action(0, PlayerActionType.CHECK)


def test_short_all_in_raise_does_not_reopen_betting_to_prior_raiser() -> None:
    state = GameState.start_new_hand(
        players(1000, 70, 1000),
        button_seat_index=0,
        small_blind=10,
        big_blind=20,
        deck=Deck.ordered(),
    )

    state.apply_action(0, PlayerActionType.RAISE, amount=60)
    state.apply_action(1, PlayerActionType.ALL_IN)
    state.apply_action(2, PlayerActionType.CALL)

    assert state.current_actor_seat_index == 0
    assert PlayerActionType.RAISE not in state.legal_actions_for(0)
    assert PlayerActionType.ALL_IN not in state.legal_actions_for(0)

    with pytest.raises(InvalidGameAction, match="not reopened"):
        state.apply_action(0, PlayerActionType.ALL_IN)

    state.apply_action(0, PlayerActionType.CALL)

    assert state.phase == BettingPhase.FLOP
    assert state.current_bet == 0


def test_all_in_side_pots_are_distributed_at_showdown() -> None:
    deck = scripted_deck(
        "Kc Kh Ah Qc Jc 5c 7d 2h 3d 4s 8d 9c Td Kd"
    )
    state = GameState.start_new_hand(
        players(100, 300, 1000),
        button_seat_index=0,
        small_blind=10,
        big_blind=20,
        deck=deck,
    )

    state.apply_action(0, PlayerActionType.ALL_IN)
    state.apply_action(1, PlayerActionType.ALL_IN)
    state.apply_action(2, PlayerActionType.CALL)

    assert state.phase == BettingPhase.FINISHED
    assert [str(card) for card in state.community_cards] == [
        "2h",
        "3d",
        "4s",
        "9c",
        "Kd",
    ]
    assert chips_by_seat(state) == {0: 300, 1: 400, 2: 700}
    assert state.result is not None
    assert [distribution.amount for distribution in state.result.pot_distributions] == [
        300,
        400,
    ]
    assert [
        distribution.winner_seat_indexes
        for distribution in state.result.pot_distributions
    ] == [(0,), (1,)]
