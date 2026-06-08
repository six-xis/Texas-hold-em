from __future__ import annotations

import pytest

from app.poker.betting import (
    InvalidBettingAction,
    amount_to_call,
    legal_actions,
    plan_betting_action,
)
from app.poker.enums import PlayerActionType


def test_amount_to_call_never_goes_negative() -> None:
    assert amount_to_call(player_current_bet=100, table_current_bet=80) == 0
    assert amount_to_call(player_current_bet=20, table_current_bet=80) == 60


def test_check_is_rejected_when_facing_bet() -> None:
    with pytest.raises(InvalidBettingAction, match="Cannot check"):
        plan_betting_action(
            action_type=PlayerActionType.CHECK,
            amount=0,
            player_chips=500,
            player_current_bet=20,
            table_current_bet=100,
            min_raise=100,
            big_blind=100,
        )


def test_call_can_put_short_stack_all_in() -> None:
    decision = plan_betting_action(
        action_type=PlayerActionType.CALL,
        amount=0,
        player_chips=40,
        player_current_bet=20,
        table_current_bet=100,
        min_raise=100,
        big_blind=100,
    )

    assert decision.commit_amount == 40
    assert decision.target_bet == 60
    assert decision.new_table_bet == 100
    assert not decision.is_full_raise


def test_raise_must_reach_minimum_unless_it_is_all_in() -> None:
    with pytest.raises(InvalidBettingAction, match="Minimum"):
        plan_betting_action(
            action_type=PlayerActionType.RAISE,
            amount=130,
            player_chips=1000,
            player_current_bet=100,
            table_current_bet=100,
            min_raise=100,
            big_blind=100,
        )

    short_all_in_raise = plan_betting_action(
        action_type=PlayerActionType.RAISE,
        amount=130,
        player_chips=30,
        player_current_bet=100,
        table_current_bet=100,
        min_raise=100,
        big_blind=100,
    )

    assert short_all_in_raise.target_bet == 130
    assert not short_all_in_raise.is_full_raise
    assert short_all_in_raise.new_min_raise == 100


def test_full_raise_updates_min_raise_to_raise_delta() -> None:
    decision = plan_betting_action(
        action_type=PlayerActionType.RAISE,
        amount=350,
        player_chips=500,
        player_current_bet=100,
        table_current_bet=150,
        min_raise=100,
        big_blind=100,
    )

    assert decision.commit_amount == 250
    assert decision.new_table_bet == 350
    assert decision.new_min_raise == 200
    assert decision.is_full_raise


def test_legal_actions_hide_raise_when_betting_was_not_reopened() -> None:
    actions = legal_actions(
        player_chips=500,
        player_current_bet=300,
        table_current_bet=340,
        min_raise=200,
        big_blind=100,
        can_raise=False,
    )

    action_types = {action.action_type for action in actions}

    assert PlayerActionType.FOLD in action_types
    assert PlayerActionType.CALL in action_types
    assert PlayerActionType.RAISE not in action_types
    assert PlayerActionType.ALL_IN not in action_types


def test_legal_actions_offer_raise_not_bet_when_current_bet_is_matched() -> None:
    actions = legal_actions(
        player_chips=500,
        player_current_bet=100,
        table_current_bet=100,
        min_raise=100,
        big_blind=100,
        can_raise=True,
    )

    action_types = {action.action_type for action in actions}

    assert PlayerActionType.CHECK in action_types
    assert PlayerActionType.RAISE in action_types
    assert PlayerActionType.BET not in action_types
