from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from app.poker.betting import (
    InvalidBettingAction,
    LegalAction,
    legal_actions,
    plan_betting_action,
)
from app.poker.card import Card
from app.poker.deck import Deck
from app.poker.enums import BettingPhase, PlayerActionType
from app.poker.hand_evaluator import HandEvaluation, HandEvaluator
from app.poker.side_pot import (
    PlayerContribution,
    PotShare,
    SidePot,
    calculate_side_pots,
    split_pot_amount,
)

MAX_SEATS = 20


class InvalidGameAction(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    seat_index: int
    player_id: str
    nickname: str
    chips: int


@dataclass(slots=True)
class SeatState:
    seat_index: int
    player_id: str
    nickname: str
    chips: int
    hole_cards: list[Card] = field(default_factory=list)
    current_bet: int = 0
    total_committed: int = 0
    has_folded: bool = False
    is_all_in: bool = False
    is_ready: bool = True
    has_acted_this_round: bool = False
    last_action: PlayerActionType | None = None

    @property
    def can_act(self) -> bool:
        return not self.has_folded and not self.is_all_in and self.chips > 0


@dataclass(frozen=True, slots=True)
class ShowdownHand:
    seat_index: int
    evaluation: HandEvaluation


@dataclass(frozen=True, slots=True)
class PotDistribution:
    pot_index: int
    amount: int
    eligible_seat_indexes: tuple[int, ...]
    winner_seat_indexes: tuple[int, ...]
    shares: tuple[PotShare, ...]


@dataclass(frozen=True, slots=True)
class WinnerResult:
    seat_index: int
    amount: int
    hand_category_name: str | None = None


@dataclass(frozen=True, slots=True)
class HandResult:
    winners: tuple[WinnerResult, ...]
    pot_distributions: tuple[PotDistribution, ...]
    showdown_hands: tuple[ShowdownHand, ...] = ()


@dataclass(slots=True)
class GameState:
    seats: list[SeatState]
    deck: Deck
    small_blind: int
    big_blind: int
    button_seat_index: int
    phase: BettingPhase = BettingPhase.PREFLOP
    community_cards: list[Card] = field(default_factory=list)
    burn_cards: list[Card] = field(default_factory=list)
    small_blind_seat_index: int | None = None
    big_blind_seat_index: int | None = None
    current_actor_seat_index: int | None = None
    current_bet: int = 0
    min_raise: int = 0
    result: HandResult | None = None
    max_seats: int = MAX_SEATS

    @classmethod
    def start_new_hand(
        cls,
        players: Sequence[PlayerProfile],
        *,
        button_seat_index: int,
        small_blind: int,
        big_blind: int,
        deck: Deck | None = None,
        max_seats: int = MAX_SEATS,
    ) -> "GameState":
        _validate_new_hand(
            players=players,
            button_seat_index=button_seat_index,
            small_blind=small_blind,
            big_blind=big_blind,
            max_seats=max_seats,
        )

        seats = [
            SeatState(
                seat_index=player.seat_index,
                player_id=player.player_id,
                nickname=player.nickname,
                chips=player.chips,
            )
            for player in sorted(players, key=lambda player: player.seat_index)
        ]
        state = cls(
            seats=seats,
            deck=deck or Deck(),
            small_blind=small_blind,
            big_blind=big_blind,
            button_seat_index=button_seat_index,
            min_raise=big_blind,
            max_seats=max_seats,
        )

        if len(seats) == 2:
            state.small_blind_seat_index = button_seat_index
            state.big_blind_seat_index = state._first_seat_after(button_seat_index)
        else:
            state.small_blind_seat_index = state._first_seat_after(button_seat_index)
            state.big_blind_seat_index = state._first_seat_after(state.small_blind_seat_index)

        state._post_blind(state.small_blind_seat_index, small_blind)
        state._post_blind(state.big_blind_seat_index, big_blind)
        state._deal_hole_cards()
        state.current_actor_seat_index = state._next_player_needing_action_after(
            state.big_blind_seat_index
        )
        state._resolve_automatic_progression()
        return state

    @property
    def pot_total(self) -> int:
        return sum(seat.total_committed for seat in self.seats)

    @property
    def active_seats(self) -> tuple[SeatState, ...]:
        return tuple(seat for seat in self.seats if not seat.has_folded)

    def seat_by_index(self, seat_index: int) -> SeatState:
        for seat in self.seats:
            if seat.seat_index == seat_index:
                return seat
        raise InvalidGameAction(f"Seat is not in the hand: {seat_index}")

    def legal_actions_for(self, seat_index: int) -> tuple[PlayerActionType, ...]:
        return tuple(action.action_type for action in self.legal_action_details_for(seat_index))

    def legal_action_details_for(self, seat_index: int) -> tuple[LegalAction, ...]:
        if self.current_actor_seat_index != seat_index:
            return ()

        seat = self.seat_by_index(seat_index)
        if not seat.can_act:
            return ()

        can_raise = not (
            seat.has_acted_this_round and self.current_bet > seat.current_bet
        )
        return legal_actions(
            player_chips=seat.chips,
            player_current_bet=seat.current_bet,
            table_current_bet=self.current_bet,
            min_raise=self.min_raise,
            big_blind=self.big_blind,
            can_raise=can_raise,
        )

    def apply_action(
        self,
        seat_index: int,
        action_type: PlayerActionType,
        *,
        amount: int = 0,
    ) -> None:
        if self.phase not in {
            BettingPhase.PREFLOP,
            BettingPhase.FLOP,
            BettingPhase.TURN,
            BettingPhase.RIVER,
        }:
            raise InvalidGameAction("The hand is not in an actionable phase")
        if self.current_actor_seat_index != seat_index:
            raise InvalidGameAction("It is not this seat's turn")

        seat = self.seat_by_index(seat_index)
        if not seat.can_act:
            raise InvalidGameAction("This seat cannot act")

        normalized_action = PlayerActionType(action_type)
        self._reject_reopened_raise_if_needed(seat, normalized_action)

        try:
            decision = plan_betting_action(
                action_type=normalized_action,
                amount=amount,
                player_chips=seat.chips,
                player_current_bet=seat.current_bet,
                table_current_bet=self.current_bet,
                min_raise=self.min_raise,
                big_blind=self.big_blind,
            )
        except InvalidBettingAction as exc:
            raise InvalidGameAction(str(exc)) from exc

        if decision.normalized_action == PlayerActionType.FOLD:
            seat.has_folded = True
            seat.has_acted_this_round = True
            seat.last_action = PlayerActionType.FOLD
        else:
            self._commit_chips(seat, decision.commit_amount)
            seat.has_acted_this_round = True
            seat.last_action = decision.normalized_action

            previous_table_bet = self.current_bet
            self.current_bet = decision.new_table_bet
            self.min_raise = decision.new_min_raise
            if decision.is_full_raise and self.current_bet > previous_table_bet:
                self._reset_action_after_full_raise(raiser=seat)

        self._resolve_after_action(start_after=seat.seat_index)

    def _reject_reopened_raise_if_needed(
        self,
        seat: SeatState,
        action_type: PlayerActionType,
    ) -> None:
        if not (seat.has_acted_this_round and self.current_bet > seat.current_bet):
            return
        if action_type == PlayerActionType.RAISE:
            raise InvalidGameAction("Betting was not reopened by a full raise")
        if action_type == PlayerActionType.ALL_IN:
            call_amount = self.current_bet - seat.current_bet
            if seat.chips > call_amount:
                raise InvalidGameAction("Betting was not reopened by a full raise")

    def _resolve_after_action(self, *, start_after: int) -> None:
        if self._finish_if_only_one_player_left():
            return
        if self._betting_closed_because_all_remaining_opponents_are_all_in():
            self._deal_remaining_community_cards()
            self._finish_by_showdown()
            return
        if self._betting_round_is_complete():
            self._advance_after_betting_round()
            return

        self.current_actor_seat_index = self._next_player_needing_action_after(start_after)

    def _resolve_automatic_progression(self) -> None:
        if self._finish_if_only_one_player_left():
            return
        if self._betting_closed_because_all_remaining_opponents_are_all_in():
            self._deal_remaining_community_cards()
            self._finish_by_showdown()

    def _advance_after_betting_round(self) -> None:
        if self.phase == BettingPhase.PREFLOP:
            self._start_next_street(BettingPhase.FLOP, cards_to_deal=3)
            return
        if self.phase == BettingPhase.FLOP:
            self._start_next_street(BettingPhase.TURN, cards_to_deal=1)
            return
        if self.phase == BettingPhase.TURN:
            self._start_next_street(BettingPhase.RIVER, cards_to_deal=1)
            return
        if self.phase == BettingPhase.RIVER:
            self._finish_by_showdown()
            return

        raise InvalidGameAction(f"Cannot advance from phase: {self.phase}")

    def _start_next_street(self, phase: BettingPhase, *, cards_to_deal: int) -> None:
        self.burn_cards.append(self.deck.burn())
        self.community_cards.extend(self.deck.deal(cards_to_deal))
        self.phase = phase
        self.current_bet = 0
        self.min_raise = self.big_blind
        for seat in self.seats:
            seat.current_bet = 0
            seat.has_acted_this_round = False

        if self._betting_closed_because_all_remaining_opponents_are_all_in():
            self._deal_remaining_community_cards()
            self._finish_by_showdown()
            return

        self.current_actor_seat_index = self._next_player_needing_action_after(
            self.button_seat_index
        )

    def _betting_round_is_complete(self) -> bool:
        actionable = [seat for seat in self.seats if seat.can_act]
        if not actionable:
            return True

        return all(
            seat.has_acted_this_round and seat.current_bet == self.current_bet
            for seat in actionable
        )

    def _betting_closed_because_all_remaining_opponents_are_all_in(self) -> bool:
        active = [seat for seat in self.seats if not seat.has_folded]
        if len(active) <= 1:
            return False

        players_with_chips = [seat for seat in active if not seat.is_all_in]
        all_bets_matched_or_all_in = all(
            seat.is_all_in or seat.current_bet == self.current_bet
            for seat in active
        )
        return len(players_with_chips) <= 1 and all_bets_matched_or_all_in

    def _finish_if_only_one_player_left(self) -> bool:
        active = [seat for seat in self.seats if not seat.has_folded]
        if len(active) != 1:
            return False

        winner = active[0]
        amount = self.pot_total
        winner.chips += amount
        share = PotShare(seat_index=winner.seat_index, amount=amount)
        distribution = PotDistribution(
            pot_index=0,
            amount=amount,
            eligible_seat_indexes=(winner.seat_index,),
            winner_seat_indexes=(winner.seat_index,),
            shares=(share,),
        )
        self.result = HandResult(
            winners=(WinnerResult(seat_index=winner.seat_index, amount=amount),),
            pot_distributions=(distribution,),
        )
        self.phase = BettingPhase.FINISHED
        self.current_actor_seat_index = None
        return True

    def _finish_by_showdown(self) -> None:
        if len(self.community_cards) < 5:
            self._deal_remaining_community_cards()

        self.phase = BettingPhase.SHOWDOWN
        active = [seat for seat in self.seats if not seat.has_folded]
        evaluations = {
            seat.seat_index: HandEvaluator.evaluate([*seat.hole_cards, *self.community_cards])
            for seat in active
        }
        showdown_hands = tuple(
            ShowdownHand(seat_index=seat_index, evaluation=evaluation)
            for seat_index, evaluation in evaluations.items()
        )

        side_pots = calculate_side_pots(
            PlayerContribution(
                seat_index=seat.seat_index,
                total_committed=seat.total_committed,
                has_folded=seat.has_folded,
            )
            for seat in self.seats
        )
        distributions: list[PotDistribution] = []
        for pot_index, pot in enumerate(side_pots):
            distribution = self._distribute_side_pot(
                pot_index=pot_index,
                pot=pot,
                evaluations=evaluations,
            )
            distributions.append(distribution)

        self.result = HandResult(
            winners=self._build_winner_results(distributions, showdown_hands),
            pot_distributions=tuple(distributions),
            showdown_hands=showdown_hands,
        )
        self.phase = BettingPhase.FINISHED
        self.current_actor_seat_index = None

    def _distribute_side_pot(
        self,
        *,
        pot_index: int,
        pot: SidePot,
        evaluations: dict[int, HandEvaluation],
    ) -> PotDistribution:
        eligible_evaluations = {
            seat_index: evaluations[seat_index]
            for seat_index in pot.eligible_seat_indexes
            if seat_index in evaluations
        }
        if not eligible_evaluations:
            raise InvalidGameAction("No eligible players for side pot")

        best_evaluation = max(eligible_evaluations.values())
        winner_seats = tuple(
            seat_index
            for seat_index, evaluation in eligible_evaluations.items()
            if evaluation == best_evaluation
        )
        shares = split_pot_amount(
            pot.amount,
            winner_seats,
            button_seat_index=self.button_seat_index,
            max_seats=self.max_seats,
        )
        for share in shares:
            self.seat_by_index(share.seat_index).chips += share.amount

        return PotDistribution(
            pot_index=pot_index,
            amount=pot.amount,
            eligible_seat_indexes=pot.eligible_seat_indexes,
            winner_seat_indexes=winner_seats,
            shares=shares,
        )

    def _build_winner_results(
        self,
        distributions: Iterable[PotDistribution],
        showdown_hands: Iterable[ShowdownHand],
    ) -> tuple[WinnerResult, ...]:
        won_amount_by_seat: defaultdict[int, int] = defaultdict(int)
        for distribution in distributions:
            for share in distribution.shares:
                won_amount_by_seat[share.seat_index] += share.amount

        hand_name_by_seat = {
            hand.seat_index: hand.evaluation.category_name
            for hand in showdown_hands
        }
        return tuple(
            WinnerResult(
                seat_index=seat_index,
                amount=amount,
                hand_category_name=hand_name_by_seat.get(seat_index),
            )
            for seat_index, amount in sorted(won_amount_by_seat.items())
        )

    def _deal_remaining_community_cards(self) -> None:
        while len(self.community_cards) < 5:
            if len(self.community_cards) == 0:
                self.burn_cards.append(self.deck.burn())
                self.community_cards.extend(self.deck.deal(3))
            elif len(self.community_cards) in {3, 4}:
                self.burn_cards.append(self.deck.burn())
                self.community_cards.extend(self.deck.deal(1))
            else:
                raise InvalidGameAction("Invalid community card count")

    def _deal_hole_cards(self) -> None:
        deal_order = self._seats_after(self.button_seat_index)
        for _ in range(2):
            for seat_index in deal_order:
                self.seat_by_index(seat_index).hole_cards.append(self.deck.deal_one())

    def _post_blind(self, seat_index: int | None, amount: int) -> None:
        if seat_index is None:
            raise InvalidGameAction("Blind seat is missing")
        seat = self.seat_by_index(seat_index)
        self._commit_chips(seat, min(amount, seat.chips))
        self.current_bet = max(self.current_bet, seat.current_bet)

    def _commit_chips(self, seat: SeatState, amount: int) -> None:
        if amount < 0:
            raise InvalidGameAction("Cannot commit a negative amount")
        if amount > seat.chips:
            raise InvalidGameAction("Cannot commit more chips than the player has")
        seat.chips -= amount
        seat.current_bet += amount
        seat.total_committed += amount
        if seat.chips == 0:
            seat.is_all_in = True

    def _reset_action_after_full_raise(self, *, raiser: SeatState) -> None:
        for seat in self.seats:
            if seat is raiser:
                seat.has_acted_this_round = True
            elif seat.can_act:
                seat.has_acted_this_round = False

    def _next_player_needing_action_after(self, seat_index: int | None) -> int | None:
        if seat_index is None:
            return None
        needing_action = [
            seat.seat_index
            for seat in self.seats
            if seat.can_act
            and (not seat.has_acted_this_round or seat.current_bet < self.current_bet)
        ]
        if not needing_action:
            return None
        return _first_clockwise_seat_after(
            seat_index,
            needing_action,
            max_seats=self.max_seats,
        )

    def _first_seat_after(self, seat_index: int | None) -> int:
        if seat_index is None:
            raise InvalidGameAction("seat_index is required")
        return _first_clockwise_seat_after(
            seat_index,
            [seat.seat_index for seat in self.seats],
            max_seats=self.max_seats,
        )

    def _seats_after(self, seat_index: int) -> tuple[int, ...]:
        return tuple(
            sorted(
                (seat.seat_index for seat in self.seats),
                key=lambda candidate: (candidate - seat_index - 1) % self.max_seats,
            )
        )


def _first_clockwise_seat_after(
    seat_index: int,
    candidate_seats: Iterable[int],
    *,
    max_seats: int,
) -> int:
    candidates = tuple(candidate_seats)
    if not candidates:
        raise InvalidGameAction("No candidate seats are available")
    return min(
        candidates,
        key=lambda candidate: (candidate - seat_index - 1) % max_seats,
    )


def _validate_new_hand(
    *,
    players: Sequence[PlayerProfile],
    button_seat_index: int,
    small_blind: int,
    big_blind: int,
    max_seats: int,
) -> None:
    if not 2 <= len(players) <= max_seats:
        raise ValueError(f"A hand requires between 2 and {max_seats} players")
    if not 0 <= button_seat_index < max_seats:
        raise ValueError("button_seat_index is outside the table")
    if small_blind <= 0 or big_blind <= 0:
        raise ValueError("Blinds must be positive")
    if small_blind > big_blind:
        raise ValueError("small_blind cannot exceed big_blind")

    seen_seats: set[int] = set()
    button_found = False
    for player in players:
        if not 0 <= player.seat_index < max_seats:
            raise ValueError(f"seat_index is outside the table: {player.seat_index}")
        if player.seat_index in seen_seats:
            raise ValueError(f"Duplicate seat_index: {player.seat_index}")
        if player.chips <= 0:
            raise ValueError("Players must start the hand with chips")
        seen_seats.add(player.seat_index)
        button_found = button_found or player.seat_index == button_seat_index

    if not button_found:
        raise ValueError("button_seat_index must point at a player in the hand")
