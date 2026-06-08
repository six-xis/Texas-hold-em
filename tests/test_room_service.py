from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.poker.enums import BettingPhase, PlayerActionType
from app.services.room_service import RoomService, RoomServiceError, RoomStatus


def test_create_join_sit_ready_and_start_game() -> None:
    service = RoomService()
    room, host = service.create_room(
        nickname="Alice",
        small_blind=5,
        big_blind=10,
        ai_enabled_by_default=True,
    )
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)

    assert room.status == RoomStatus.PLAYING
    assert room.current_game is not None
    assert room.current_game.phase == BettingPhase.PREFLOP
    assert room.current_game.current_actor_seat_index == 0

    alice_view = service.serialize_room(room, viewer_guest_id=host.guest_id)
    bob_seat = alice_view.seats[1]

    assert alice_view.viewer.can_act
    assert alice_view.seats[0].hole_cards != ["hidden", "hidden"]
    assert bob_seat.hole_cards == ["hidden", "hidden"]
    assert alice_view.hand_number == 1
    assert alice_view.player_count == 2
    assert alice_view.action_started_at is not None
    assert alice_view.action_expires_at is not None
    assert alice_view.action_timeout_seconds == 30
    assert alice_view.action_options.to_call == 5
    assert alice_view.action_options.min_raise_to == 20
    assert alice_view.action_options.all_in_amount == 9995
    assert alice_view.seats[0].position_label == "BTN/SB"
    assert alice_view.seats[1].position_label == "BB"
    assert alice_view.seats[0].time_cards_remaining == 5
    assert alice_view.ai_assistant.enabled is True
    assert alice_view.ai_assistant.hand_label
    assert any(event.type == "hand_started" for event in alice_view.event_log)


def test_room_enforces_twenty_member_limit() -> None:
    service = RoomService()
    room, _ = service.create_room(nickname="Host")

    for index in range(19):
        service.join_room(room_code=room.room_code, nickname=f"P{index}")

    with pytest.raises(RoomServiceError) as exc_info:
        service.join_room(room_code=room.room_code, nickname="Overflow")

    assert exc_info.value.code == "ROOM_FULL"


def test_only_host_can_start_game() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice")
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)

    with pytest.raises(RoomServiceError) as exc_info:
        service.start_game(room_code=room.room_code, guest_id=bob.guest_id)

    assert exc_info.value.code == "NOT_HOST"


def test_player_actions_advance_game_through_service() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)

    room = service.player_action(
        room_code=room.room_code,
        guest_id=host.guest_id,
        action=PlayerActionType.CALL.value,
    )
    room = service.player_action(
        room_code=room.room_code,
        guest_id=bob.guest_id,
        action=PlayerActionType.CHECK.value,
    )

    assert room.current_game is not None
    assert room.current_game.phase == BettingPhase.FLOP
    assert room.status == RoomStatus.PLAYING


def test_disconnect_and_reconnect_preserves_seat() -> None:
    service = RoomService()
    room, guest = service.create_room(nickname="Alice")

    service.sit_down(room_code=room.room_code, guest_id=guest.guest_id, seat_index=4)
    disconnected = service.disconnect(room_code=room.room_code, guest_id=guest.guest_id)

    assert disconnected is not None
    assert disconnected.members[guest.guest_id].is_connected is False

    room, reconnected_guest = service.reconnect(
        room_code=room.room_code,
        guest_id=guest.guest_id,
    )
    view = service.serialize_room(room, viewer_guest_id=guest.guest_id)

    assert reconnected_guest.is_connected is True
    assert view.viewer.seat_index == 4
    assert view.seats[4].is_connected is True


def test_room_summary_and_event_log_are_available() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", ai_enabled_by_default=True)
    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=2)

    summaries = service.list_rooms()
    view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert summaries[0].room_code == room.room_code
    assert summaries[0].ai_enabled_by_default is True
    assert view.ai_enabled_by_default is True
    assert summaries[0].occupied_seats == 1
    assert any(event.type == "seat_taken" for event in view.event_log)


def test_host_can_add_ready_bot_to_empty_seat() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice")

    room = service.add_bot(room_code=room.room_code, guest_id=host.guest_id)
    view = service.serialize_room(room, viewer_guest_id=host.guest_id)
    bot_seats = [seat for seat in view.seats if seat.is_bot]

    assert len(bot_seats) == 1
    assert bot_seats[0].occupied is True
    assert bot_seats[0].is_ready is True
    assert bot_seats[0].nickname is not None
    assert bot_seats[0].nickname.startswith("智能机器人")
    assert any(event.type == "bot_added" for event in view.event_log)


def test_non_host_cannot_add_bot() -> None:
    service = RoomService()
    room, _ = service.create_room(nickname="Alice")
    _, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    with pytest.raises(RoomServiceError) as exc_info:
        service.add_bot(room_code=room.room_code, guest_id=bob.guest_id)

    assert exc_info.value.code == "NOT_HOST"


def test_host_can_pause_resume_and_end_current_game() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)

    room = service.set_paused(
        room_code=room.room_code,
        guest_id=host.guest_id,
        is_paused=True,
    )
    paused_view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert room.is_paused is True
    assert paused_view.is_paused is True
    assert paused_view.viewer.can_act is False
    assert paused_view.viewer.legal_actions == []
    assert paused_view.action_started_at is None
    assert paused_view.action_expires_at is None
    assert any(event.type == "game_paused" for event in paused_view.event_log)
    with pytest.raises(RoomServiceError) as exc_info:
        service.player_action(
            room_code=room.room_code,
            guest_id=host.guest_id,
            action=PlayerActionType.CALL.value,
        )
    assert exc_info.value.code == "GAME_PAUSED"

    room = service.set_paused(
        room_code=room.room_code,
        guest_id=host.guest_id,
        is_paused=False,
    )
    resumed_view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert room.is_paused is False
    assert resumed_view.viewer.can_act is True
    assert resumed_view.action_started_at is not None
    assert resumed_view.action_expires_at is not None
    assert any(event.type == "game_resumed" for event in resumed_view.event_log)

    room = service.end_game(room_code=room.room_code, guest_id=host.guest_id)
    ended_view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert room.status == RoomStatus.WAITING
    assert room.current_game is None
    assert room.members[host.guest_id].chips == 10000
    assert room.members[bob.guest_id].chips == 10000
    assert ended_view.is_paused is False
    assert ended_view.phase == "waiting"
    assert ended_view.seats[0].is_ready is False
    assert ended_view.seats[1].is_ready is False
    assert any(event.type == "game_ended" for event in ended_view.event_log)


def test_bot_auto_acts_after_human_action() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    room = service.add_bot(room_code=room.room_code, guest_id=host.guest_id)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)

    room = service.player_action(
        room_code=room.room_code,
        guest_id=host.guest_id,
        action=PlayerActionType.CALL.value,
    )

    assert room.current_game is not None
    assert room.current_game.phase == BettingPhase.FLOP
    assert room.current_game.current_actor_seat_index == 0
    assert any(event.type == "bot_action" for event in room.event_log)


def test_ready_is_only_reset_after_every_twentieth_hand() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)

    for hand_number in range(1, 21):
        room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)
        assert room.hand_number == hand_number
        assert room.current_game is not None
        actor_guest_id = _guest_id_for_actor(room)
        room = service.player_action(
            room_code=room.room_code,
            guest_id=actor_guest_id,
            action=PlayerActionType.FOLD.value,
        )
        view = service.serialize_room(room, viewer_guest_id=host.guest_id)
        assert room.status == RoomStatus.WAITING
        assert view.last_result is not None

        if hand_number < 20:
            assert view.ready_break_required is False
            assert view.seats[0].is_ready is True
            assert view.seats[1].is_ready is True
        else:
            assert view.ready_break_required is True
            assert view.seats[0].is_ready is False
            assert view.seats[1].is_ready is False
            assert any(event.type == "ready_break" for event in view.event_log)

    with pytest.raises(RoomServiceError) as exc_info:
        service.start_game(room_code=room.room_code, guest_id=host.guest_id)
    assert exc_info.value.code == "NOT_ALL_READY"

    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)

    assert room.hand_number == 21
    assert room.status == RoomStatus.PLAYING


def test_training_chips_are_awarded_after_bust_and_next_hand_can_start() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    room.members[host.guest_id].chips = 100
    room.members[bob.guest_id].chips = 100
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)
    actor_guest_id = _guest_id_for_actor(room)
    room = service.player_action(
        room_code=room.room_code,
        guest_id=actor_guest_id,
        action=PlayerActionType.ALL_IN.value,
    )
    assert room.current_game is not None
    if room.current_game.phase != BettingPhase.FINISHED:
        actor_guest_id = _guest_id_for_actor(room)
        room = service.player_action(
            room_code=room.room_code,
            guest_id=actor_guest_id,
            action=PlayerActionType.CALL.value,
        )

    awarded_members = [
        member for member in room.members.values() if member.training_chips_awarded
    ]
    assert room.status == RoomStatus.WAITING
    assert awarded_members
    assert awarded_members[0].chips >= 5000
    assert awarded_members[0].training_chips_awarded == 5000
    assert any(event.type == "training_chips_awarded" for event in room.event_log)
    assert any("获得 5000 训练筹码" in message.content for message in room.chat_messages)

    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)
    assert room.status == RoomStatus.PLAYING
    assert room.hand_number == 2


def test_training_chips_manual_claim_requires_zero_stack_and_no_active_hand() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)

    with pytest.raises(RoomServiceError) as exc_info:
        service.award_training_chips(room_code=room.room_code, guest_id=host.guest_id)
    assert exc_info.value.code == "TRAINING_CHIPS_NOT_ALLOWED"

    room.members[host.guest_id].chips = 0
    room = service.award_training_chips(room_code=room.room_code, guest_id=host.guest_id)
    view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert room.members[host.guest_id].chips == 5000
    assert room.members[host.guest_id].training_chips_awarded == 5000
    assert view.seats[0].training_chips_awarded == 5000
    assert any(event.type == "training_chips_awarded" for event in view.event_log)
    assert any(message.is_system and "获得 5000 训练筹码" in message.content for message in view.chat_messages)

    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)
    with pytest.raises(RoomServiceError) as exc_info:
        service.award_training_chips(room_code=room.room_code, guest_id=host.guest_id)
    assert exc_info.value.code == "HAND_IN_PROGRESS"


def test_time_card_extends_current_actor_deadline() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)
    actor_guest_id = _guest_id_for_actor(room)
    before_deadline = room.action_deadline_at

    room = service.use_time_card(room_code=room.room_code, guest_id=actor_guest_id)
    view = service.serialize_room(room, viewer_guest_id=actor_guest_id)

    assert before_deadline is not None
    assert room.action_deadline_at is not None
    assert (room.action_deadline_at - before_deadline).total_seconds() >= 29
    assert room.members[actor_guest_id].time_cards_remaining == 4
    assert view.seats[view.viewer.seat_index or 0].time_cards_remaining == 4
    assert any(event.type == "time_card_used" for event in view.event_log)


def test_timeout_auto_uses_time_card_then_folds_when_empty() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", small_blind=5, big_blind=10)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    service.sit_down(room_code=room.room_code, guest_id=host.guest_id, seat_index=0)
    service.sit_down(room_code=room.room_code, guest_id=bob.guest_id, seat_index=1)
    service.set_ready(room_code=room.room_code, guest_id=host.guest_id, is_ready=True)
    service.set_ready(room_code=room.room_code, guest_id=bob.guest_id, is_ready=True)
    room = service.start_game(room_code=room.room_code, guest_id=host.guest_id)
    actor_guest_id = _guest_id_for_actor(room)
    room.members[actor_guest_id].time_cards_remaining = 1
    room.action_deadline_at = datetime.now(UTC) - timedelta(seconds=1)

    timeout_room = service.process_timeouts(room_code=room.room_code)

    assert timeout_room is room
    assert room.status == RoomStatus.PLAYING
    assert room.members[actor_guest_id].time_cards_remaining == 0
    assert room.action_deadline_at is not None
    assert room.action_deadline_at > datetime.now(UTC)
    assert any(event.type == "time_card_used" for event in room.event_log)

    room.action_deadline_at = datetime.now(UTC) - timedelta(seconds=1)
    timeout_room = service.process_timeouts(room_code=room.room_code)
    view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert timeout_room is room
    assert room.status == RoomStatus.WAITING
    assert view.last_result is not None
    assert any(event.type == "auto_fold" for event in view.event_log)


def test_chat_messages_are_validated_and_trimmed_to_recent_100() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice")

    with pytest.raises(RoomServiceError) as exc_info:
        service.send_chat_message(room_code=room.room_code, guest_id=host.guest_id, content="  ")
    assert exc_info.value.code == "EMPTY_MESSAGE"

    with pytest.raises(RoomServiceError) as exc_info:
        service.send_chat_message(room_code=room.room_code, guest_id=host.guest_id, content="x" * 201)
    assert exc_info.value.code == "MESSAGE_TOO_LONG"

    for index in range(101):
        room, message = service.send_chat_message(
            room_code=room.room_code,
            guest_id=host.guest_id,
            content=f" 消息 {index} ",
        )

    view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert message.content == "消息 100"
    assert len(view.chat_messages) == 100
    assert view.chat_messages[-1].content == "消息 100"
    assert view.chat_messages[-1].guest_id == host.guest_id


def test_only_host_can_toggle_room_ai_assistant() -> None:
    service = RoomService()
    room, host = service.create_room(nickname="Alice", ai_enabled_by_default=False)
    room, bob = service.join_room(room_code=room.room_code, nickname="Bob")

    with pytest.raises(RoomServiceError) as exc_info:
        service.set_ai_enabled(room_code=room.room_code, guest_id=bob.guest_id, is_enabled=True)
    assert exc_info.value.code == "NOT_HOST"

    room = service.set_ai_enabled(room_code=room.room_code, guest_id=host.guest_id, is_enabled=True)
    view = service.serialize_room(room, viewer_guest_id=host.guest_id)

    assert view.ai_enabled_by_default is True
    assert any(event.type == "ai_enabled_changed" for event in view.event_log)

    room = service.set_ai_enabled(room_code=room.room_code, guest_id=host.guest_id, is_enabled=False)
    view = service.serialize_room(room, viewer_guest_id=bob.guest_id)

    assert view.ai_enabled_by_default is False
    assert view.ai_assistant.enabled is False


def _guest_id_for_actor(room) -> str:
    assert room.current_game is not None
    actor_index = room.current_game.current_actor_seat_index
    assert actor_index is not None
    for seat in room.seats:
        if seat.seat_index == actor_index:
            assert seat.guest_id is not None
            return seat.guest_id
    raise AssertionError("actor seat not found")
