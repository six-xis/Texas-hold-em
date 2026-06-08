from __future__ import annotations

from dataclasses import dataclass

from app.poker.enums import PlayerActionType


class InvalidBettingAction(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BettingDecision:
    normalized_action: PlayerActionType
    commit_amount: int
    target_bet: int
    new_table_bet: int
    new_min_raise: int
    is_full_raise: bool = False


@dataclass(frozen=True, slots=True)
class LegalAction:
    action_type: PlayerActionType
    call_amount: int = 0
    min_amount: int | None = None
    max_amount: int | None = None


def amount_to_call(*, player_current_bet: int, table_current_bet: int) -> int:
    return max(0, table_current_bet - player_current_bet)


def plan_betting_action(
    *,
    action_type: PlayerActionType,
    amount: int,
    player_chips: int,
    player_current_bet: int,
    table_current_bet: int,
    min_raise: int,
    big_blind: int,
) -> BettingDecision:
    _validate_common_inputs(
        amount=amount,
        player_chips=player_chips,
        player_current_bet=player_current_bet,
        table_current_bet=table_current_bet,
        min_raise=min_raise,
        big_blind=big_blind,
    )

    to_call = amount_to_call(
        player_current_bet=player_current_bet,
        table_current_bet=table_current_bet,
    )
    max_target_bet = player_current_bet + player_chips

    if action_type == PlayerActionType.FOLD:
        return BettingDecision(
            normalized_action=PlayerActionType.FOLD,
            commit_amount=0,
            target_bet=player_current_bet,
            new_table_bet=table_current_bet,
            new_min_raise=min_raise,
        )

    if action_type == PlayerActionType.CHECK:
        if to_call != 0:
            raise InvalidBettingAction("Cannot check while facing a bet")
        return BettingDecision(
            normalized_action=PlayerActionType.CHECK,
            commit_amount=0,
            target_bet=player_current_bet,
            new_table_bet=table_current_bet,
            new_min_raise=min_raise,
        )

    if action_type == PlayerActionType.CALL:
        if to_call == 0:
            raise InvalidBettingAction("Cannot call when there is no bet to call")
        commit_amount = min(player_chips, to_call)
        return BettingDecision(
            normalized_action=PlayerActionType.CALL,
            commit_amount=commit_amount,
            target_bet=player_current_bet + commit_amount,
            new_table_bet=table_current_bet,
            new_min_raise=min_raise,
        )

    if action_type == PlayerActionType.BET:
        if table_current_bet != 0:
            raise InvalidBettingAction("Cannot bet after a bet already exists")
        return _plan_aggressive_action(
            normalized_action=PlayerActionType.BET,
            target_bet=amount,
            max_target_bet=max_target_bet,
            player_current_bet=player_current_bet,
            table_current_bet=table_current_bet,
            min_raise=min_raise,
            minimum_full_amount=big_blind,
        )

    if action_type == PlayerActionType.RAISE:
        if table_current_bet == 0:
            raise InvalidBettingAction("Cannot raise before a bet exists")
        return _plan_aggressive_action(
            normalized_action=PlayerActionType.RAISE,
            target_bet=amount,
            max_target_bet=max_target_bet,
            player_current_bet=player_current_bet,
            table_current_bet=table_current_bet,
            min_raise=min_raise,
            minimum_full_amount=table_current_bet + min_raise,
        )

    if action_type == PlayerActionType.ALL_IN:
        if player_chips <= 0:
            raise InvalidBettingAction("Cannot go all-in without chips")
        target_bet = max_target_bet
        if target_bet <= table_current_bet:
            return BettingDecision(
                normalized_action=PlayerActionType.ALL_IN,
                commit_amount=player_chips,
                target_bet=target_bet,
                new_table_bet=table_current_bet,
                new_min_raise=min_raise,
            )

        full_raise_delta = (
            target_bet
            if table_current_bet == 0
            else target_bet - table_current_bet
        )
        minimum_full_delta = big_blind if table_current_bet == 0 else min_raise
        is_full_raise = full_raise_delta >= minimum_full_delta
        return BettingDecision(
            normalized_action=PlayerActionType.ALL_IN,
            commit_amount=player_chips,
            target_bet=target_bet,
            new_table_bet=target_bet,
            new_min_raise=full_raise_delta if is_full_raise else min_raise,
            is_full_raise=is_full_raise,
        )

    raise InvalidBettingAction(f"Unsupported action: {action_type}")


def legal_actions(
    *,
    player_chips: int,
    player_current_bet: int,
    table_current_bet: int,
    min_raise: int,
    big_blind: int,
    can_raise: bool = True,
) -> tuple[LegalAction, ...]:
    if player_chips <= 0:
        return ()

    to_call = amount_to_call(
        player_current_bet=player_current_bet,
        table_current_bet=table_current_bet,
    )
    max_target_bet = player_current_bet + player_chips
    actions: list[LegalAction] = []

    if to_call > 0:
        actions.append(LegalAction(PlayerActionType.FOLD))
        actions.append(
            LegalAction(
                PlayerActionType.CALL,
                call_amount=min(to_call, player_chips),
            )
        )
        if can_raise and max_target_bet > table_current_bet:
            min_raise_to = table_current_bet + min_raise
            if max_target_bet >= min_raise_to:
                actions.append(
                    LegalAction(
                        PlayerActionType.RAISE,
                        min_amount=min_raise_to,
                        max_amount=max_target_bet,
                    )
                )
        if can_raise or player_chips <= to_call:
            actions.append(LegalAction(PlayerActionType.ALL_IN, max_amount=max_target_bet))
        return tuple(actions)

    actions.append(LegalAction(PlayerActionType.CHECK))
    if can_raise:
        if table_current_bet > 0:
            min_raise_to = table_current_bet + min_raise
            if max_target_bet >= min_raise_to:
                actions.append(
                    LegalAction(
                        PlayerActionType.RAISE,
                        min_amount=min_raise_to,
                        max_amount=max_target_bet,
                    )
                )
        else:
            min_bet = min(big_blind, player_chips)
            actions.append(
                LegalAction(
                    PlayerActionType.BET,
                    min_amount=min_bet,
                    max_amount=max_target_bet,
                )
            )
    if table_current_bet == 0 or can_raise:
        actions.append(LegalAction(PlayerActionType.ALL_IN, max_amount=max_target_bet))
    return tuple(actions)


def _plan_aggressive_action(
    *,
    normalized_action: PlayerActionType,
    target_bet: int,
    max_target_bet: int,
    player_current_bet: int,
    table_current_bet: int,
    min_raise: int,
    minimum_full_amount: int,
) -> BettingDecision:
    if target_bet <= table_current_bet:
        raise InvalidBettingAction("Aggressive action must increase the table bet")
    if target_bet > max_target_bet:
        raise InvalidBettingAction("Action exceeds available chips")
    if target_bet < minimum_full_amount and target_bet != max_target_bet:
        raise InvalidBettingAction("Minimum raise or bet amount not met")

    commit_amount = target_bet - player_current_bet
    if commit_amount <= 0:
        raise InvalidBettingAction("Action must commit chips")

    raise_delta = target_bet if table_current_bet == 0 else target_bet - table_current_bet
    full_raise_delta = min_raise if table_current_bet > 0 else minimum_full_amount
    is_full_raise = target_bet >= minimum_full_amount

    return BettingDecision(
        normalized_action=normalized_action,
        commit_amount=commit_amount,
        target_bet=target_bet,
        new_table_bet=target_bet,
        new_min_raise=raise_delta if is_full_raise else full_raise_delta,
        is_full_raise=is_full_raise,
    )


def _validate_common_inputs(
    *,
    amount: int,
    player_chips: int,
    player_current_bet: int,
    table_current_bet: int,
    min_raise: int,
    big_blind: int,
) -> None:
    if amount < 0:
        raise InvalidBettingAction("amount cannot be negative")
    if player_chips < 0:
        raise InvalidBettingAction("player_chips cannot be negative")
    if player_current_bet < 0:
        raise InvalidBettingAction("player_current_bet cannot be negative")
    if table_current_bet < 0:
        raise InvalidBettingAction("table_current_bet cannot be negative")
    if min_raise <= 0:
        raise InvalidBettingAction("min_raise must be positive")
    if big_blind <= 0:
        raise InvalidBettingAction("big_blind must be positive")
