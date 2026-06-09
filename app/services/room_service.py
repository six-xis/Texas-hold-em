from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import Enum
from threading import RLock
from uuid import uuid4

from app.config import settings
from app.poker.betting import LegalAction
from app.poker.card import Card
from app.poker.enums import BettingPhase, PlayerActionType
from app.poker.game_state import (
    GameState,
    InvalidGameAction,
    PlayerProfile,
    SeatState as GameSeatState,
)
from app.poker.hand_evaluator import HandCategory, HandEvaluator
from app.schemas.game import (
    HandResultView,
    PotDistributionView,
    PotShareView,
    ShowdownHandView,
    WinnerView,
)
from app.schemas.room import (
    ActionOptionsView,
    AiAssistantView,
    ChatMessageView,
    GuestSessionView,
    RankingEntryView,
    RoomEventView,
    RoomEnvelope,
    RoomStateView,
    RoomSummaryView,
    SeatView,
    ViewerView,
)
from app.services.session_service import SessionService


DEFAULT_ACTION_TIMEOUT_SECONDS = 30
INITIAL_TIME_CARDS = 5
TIME_CARD_EXTENSION_SECONDS = 30


class RoomStatus(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    FINISHED = "finished"


class RoomServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class GuestUser:
    guest_id: str
    nickname: str
    chips: int
    training_chips_awarded: int = 0
    time_cards_remaining: int = INITIAL_TIME_CARDS
    is_bot: bool = False
    is_connected: bool = True
    joined_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class RegisteredUser:
    guest_id: str
    nickname: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class RoomSeat:
    seat_index: int
    guest_id: str | None = None
    is_ready: bool = False
    reserved_until: datetime | None = None


@dataclass(slots=True)
class RoomEvent:
    id: int
    type: str
    message: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ChatMessage:
    message_id: int
    room_code: str
    guest_id: str | None
    nickname: str
    content: str
    is_system: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Room:
    room_id: str
    room_code: str
    host_guest_id: str
    small_blind: int
    big_blind: int
    max_seats: int
    max_members: int
    ai_enabled_by_default: bool = False
    status: RoomStatus = RoomStatus.WAITING
    is_paused: bool = False
    paused_by_guest_id: str | None = None
    button_seat_index: int | None = None
    hand_number: int = 0
    action_started_at: datetime | None = None
    action_deadline_at: datetime | None = None
    action_timeout_seconds: int = DEFAULT_ACTION_TIMEOUT_SECONDS
    revision: int = 1
    members: dict[str, GuestUser] = field(default_factory=dict)
    seats: list[RoomSeat] = field(default_factory=list)
    current_game: GameState | None = None
    event_log: list[RoomEvent] = field(default_factory=list)
    chat_messages: list[ChatMessage] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def seat_for_guest(self, guest_id: str) -> RoomSeat | None:
        for seat in self.seats:
            if seat.guest_id == guest_id:
                return seat
        return None

    def seat_by_index(self, seat_index: int) -> RoomSeat:
        if not 0 <= seat_index < self.max_seats:
            raise RoomServiceError("INVALID_SEAT", "座位编号超出牌桌范围")
        return self.seats[seat_index]


class RoomService:
    def __init__(
        self,
        *,
        session_service: SessionService | None = None,
        max_members: int = settings.room_max_members,
        max_seats: int = settings.room_max_seats,
    ) -> None:
        self._session_service = session_service or SessionService(
            initial_chips=settings.guest_initial_chips
        )
        self._max_members = max_members
        self._max_seats = max_seats
        self._rooms_by_code: dict[str, Room] = {}
        self._registered_users_by_name: dict[str, RegisteredUser] = {}
        self._registered_users_by_id: dict[str, RegisteredUser] = {}
        self._lock = RLock()

    def register_user(self, *, nickname: str) -> GuestUser:
        normalized_nickname = self._session_service.normalize_nickname(nickname)
        nickname_key = self._nickname_key(normalized_nickname)
        with self._lock:
            if nickname_key in self._registered_users_by_name:
                raise RoomServiceError("USER_ALREADY_EXISTS", "这个昵称已经注册，请换一个")

            registered = RegisteredUser(
                guest_id=self._session_service.create_guest_id(),
                nickname=normalized_nickname,
            )
            self._registered_users_by_name[nickname_key] = registered
            self._registered_users_by_id[registered.guest_id] = registered
            return GuestUser(
                guest_id=registered.guest_id,
                nickname=registered.nickname,
                chips=self._session_service.initial_chips,
            )

    def create_room(
        self,
        *,
        nickname: str,
        guest_id: str | None = None,
        small_blind: int = settings.default_small_blind,
        big_blind: int = settings.default_big_blind,
        ai_enabled_by_default: bool = False,
    ) -> tuple[Room, GuestUser]:
        if small_blind <= 0 or big_blind <= 0 or small_blind > big_blind:
            raise RoomServiceError("INVALID_BLINDS", "盲注配置不合法")

        with self._lock:
            guest = self._build_guest(nickname=nickname, guest_id=guest_id)
            room_code = self._generate_room_code()
            room = Room(
                room_id=str(uuid4()),
                room_code=room_code,
                host_guest_id=guest.guest_id,
                small_blind=small_blind,
                big_blind=big_blind,
                max_seats=self._max_seats,
                max_members=self._max_members,
                ai_enabled_by_default=ai_enabled_by_default,
                members={guest.guest_id: guest},
                seats=[RoomSeat(seat_index=index) for index in range(self._max_seats)],
            )
            self._rooms_by_code[room_code] = room
            self._append_event(room, "room_created", f"{guest.nickname} 创建了房间 {room_code}")
            return room, guest

    def add_bot(self, *, room_code: str, guest_id: str) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            if room.host_guest_id != guest_id:
                raise RoomServiceError("NOT_HOST", "只有房主可以添加机器人")
            if room.status == RoomStatus.PLAYING:
                raise RoomServiceError("GAME_IN_PROGRESS", "只能在两局之间添加机器人")
            if len(room.members) >= room.max_members:
                raise RoomServiceError("ROOM_FULL", "房间已满")

            empty_seat = next((seat for seat in room.seats if seat.guest_id is None), None)
            if empty_seat is None:
                raise RoomServiceError("NO_EMPTY_SEAT", "没有可用空座位")

            bot_number = sum(1 for member in room.members.values() if member.is_bot) + 1
            bot = GuestUser(
                guest_id=f"bot_{uuid4().hex}",
                nickname=f"智能机器人 {bot_number}",
                chips=self._session_service.initial_chips,
                is_bot=True,
                is_connected=True,
            )
            room.members[bot.guest_id] = bot
            empty_seat.guest_id = bot.guest_id
            empty_seat.is_ready = True
            self._append_event(
                room,
                "bot_added",
                f"{bot.nickname} 已加入并坐到 {empty_seat.seat_index + 1} 号座位",
            )
            self._touch(room)
            return room

    def set_paused(self, *, room_code: str, guest_id: str, is_paused: bool) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            guest = self._require_member(room, guest_id)
            if room.host_guest_id != guest_id:
                raise RoomServiceError("NOT_HOST", "只有房主可以暂停或继续牌局")
            if room.status != RoomStatus.PLAYING or room.current_game is None:
                raise RoomServiceError("GAME_NOT_RUNNING", "当前没有正在进行的牌局")

            if is_paused:
                room.is_paused = True
                room.paused_by_guest_id = guest_id
                room.action_started_at = None
                room.action_deadline_at = None
                self._append_event(room, "game_paused", f"{guest.nickname} 暂停了牌局")
            else:
                room.is_paused = False
                room.paused_by_guest_id = None
                self._append_event(room, "game_resumed", f"{guest.nickname} 继续了牌局")
                self._auto_play_bots(room)
                self._sync_actor_timer(room)

            self._touch(room)
            return room

    def end_game(self, *, room_code: str, guest_id: str) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            guest = self._require_member(room, guest_id)
            if room.host_guest_id != guest_id:
                raise RoomServiceError("NOT_HOST", "只有房主可以结束本局")
            if room.status != RoomStatus.PLAYING or room.current_game is None:
                raise RoomServiceError("GAME_NOT_RUNNING", "当前没有正在进行的牌局")

            active_player_ids = {game_seat.player_id for game_seat in room.current_game.seats}
            for game_seat in room.current_game.seats:
                member = room.members.get(game_seat.player_id)
                if member is not None:
                    member.chips = game_seat.chips + game_seat.total_committed

            for seat in room.seats:
                if seat.guest_id in active_player_ids:
                    member = room.members.get(seat.guest_id)
                    seat.is_ready = bool(member and member.is_bot)

            room.status = RoomStatus.WAITING
            room.is_paused = False
            room.paused_by_guest_id = None
            room.action_started_at = None
            room.action_deadline_at = None
            room.current_game = None
            self._append_event(room, "game_ended", f"{guest.nickname} 结束了本局，已退回本局投入筹码")
            self._touch(room)
            return room

    def join_room(
        self,
        *,
        room_code: str,
        nickname: str,
        guest_id: str | None = None,
    ) -> tuple[Room, GuestUser]:
        with self._lock:
            room = self.get_room(room_code)
            if guest_id and guest_id in room.members:
                guest = room.members[guest_id]
                registered = self._registered_users_by_id.get(guest_id)
                guest.nickname = (
                    registered.nickname
                    if registered
                    else self._session_service.normalize_nickname(nickname)
                )
                guest.is_connected = True
                guest.last_seen_at = datetime.now(UTC)
                self._append_event(room, "player_reconnected", f"{guest.nickname} 已重新连接")
                self._touch(room)
                return room, guest

            if len(room.members) >= room.max_members:
                raise RoomServiceError("ROOM_FULL", "房间已满")

            guest = self._build_guest(nickname=nickname, guest_id=guest_id)
            room.members[guest.guest_id] = guest
            self._append_event(room, "player_joined", f"{guest.nickname} 以旁观者身份加入房间")
            self._touch(room)
            return room, guest

    def get_room(self, room_code: str) -> Room:
        normalized = room_code.strip().upper()
        try:
            return self._rooms_by_code[normalized]
        except KeyError as exc:
            raise RoomServiceError("ROOM_NOT_FOUND", "房间不存在") from exc

    def reconnect(self, *, room_code: str, guest_id: str) -> tuple[Room, GuestUser]:
        with self._lock:
            room = self.get_room(room_code)
            guest = self._require_member(room, guest_id)
            guest.is_connected = True
            guest.last_seen_at = datetime.now(UTC)
            self._append_event(room, "player_reconnected", f"{guest.nickname} 已重新连接")
            self._touch(room)
            return room, guest

    def leave_room(self, *, room_code: str, guest_id: str) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)

            if self._is_guest_in_active_hand(room, guest_id):
                room.members[guest_id].is_connected = False
                room.members[guest_id].last_seen_at = datetime.now(UTC)
                self._append_event(room, "player_disconnected", f"{room.members[guest_id].nickname} 已断线")
                self._touch(room)
                return room

            seat = room.seat_for_guest(guest_id)
            if seat is not None:
                seat.guest_id = None
                seat.is_ready = False
            nickname = room.members[guest_id].nickname
            del room.members[guest_id]
            if guest_id == room.host_guest_id and room.members:
                room.host_guest_id = next(iter(room.members))
            self._append_event(room, "player_left", f"{nickname} 离开了房间")
            self._touch(room)
            return room

    def disconnect(self, *, room_code: str, guest_id: str | None) -> Room | None:
        if guest_id is None:
            return None

        with self._lock:
            try:
                room = self.get_room(room_code)
            except RoomServiceError:
                return None
            guest = room.members.get(guest_id)
            if guest is None:
                return room
            guest.is_connected = False
            guest.last_seen_at = datetime.now(UTC)
            self._append_event(room, "player_disconnected", f"{guest.nickname} 已断线")
            self._touch(room)
            return room

    def sit_down(self, *, room_code: str, guest_id: str, seat_index: int) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            target_seat = room.seat_by_index(seat_index)
            if target_seat.guest_id not in {None, guest_id}:
                raise RoomServiceError("SEAT_OCCUPIED", "座位已被占用")

            current_seat = room.seat_for_guest(guest_id)
            if current_seat is not None and current_seat.seat_index != seat_index:
                if self._is_guest_in_active_hand(room, guest_id):
                    raise RoomServiceError("GAME_IN_PROGRESS", "牌局进行中不能移动座位")
                current_seat.guest_id = None
                current_seat.is_ready = False

            target_seat.guest_id = guest_id
            target_seat.is_ready = False
            self._append_event(
                room,
                "seat_taken",
                f"{room.members[guest_id].nickname} 坐到 {seat_index + 1} 号座位",
            )
            self._touch(room)
            return room

    def stand_up(self, *, room_code: str, guest_id: str) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            if self._is_guest_in_active_hand(room, guest_id):
                raise RoomServiceError("GAME_IN_PROGRESS", "牌局进行中不能站起")

            seat = room.seat_for_guest(guest_id)
            if seat is not None:
                seat.guest_id = None
                seat.is_ready = False
                self._append_event(room, "stand_up", f"{room.members[guest_id].nickname} 站起")
                self._touch(room)
            return room

    def set_ready(self, *, room_code: str, guest_id: str, is_ready: bool) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            seat = room.seat_for_guest(guest_id)
            if seat is None:
                raise RoomServiceError("NOT_SITTED", "请先坐下再准备")
            seat.is_ready = is_ready
            self._append_event(
                room,
                "ready_changed",
                f"{room.members[guest_id].nickname} {'已准备' if is_ready else '取消准备'}",
            )
            self._touch(room)
            return room

    def start_game(self, *, room_code: str, guest_id: str) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            if room.host_guest_id != guest_id:
                raise RoomServiceError("NOT_HOST", "只有房主可以开始游戏")
            if room.status == RoomStatus.PLAYING:
                raise RoomServiceError("GAME_ALREADY_STARTED", "当前牌局已经开始")
            if self._ready_break_required(room) and not self._all_eligible_seated_players_ready(room):
                raise RoomServiceError("NOT_ALL_READY", "已完成 20 手，请所有有筹码的入座玩家重新准备")

            player_profiles = self._ready_player_profiles(room)
            if len(player_profiles) < 2:
                raise RoomServiceError("NOT_ENOUGH_PLAYERS", "至少需要两名已准备且已坐下的玩家")

            button_seat_index = self._button_for_next_hand(room, player_profiles)
            room.current_game = GameState.start_new_hand(
                player_profiles,
                button_seat_index=button_seat_index,
                small_blind=room.small_blind,
                big_blind=room.big_blind,
                max_seats=room.max_seats,
            )
            room.button_seat_index = button_seat_index
            room.status = RoomStatus.PLAYING
            room.is_paused = False
            room.paused_by_guest_id = None
            room.hand_number += 1
            self._append_event(room, "hand_started", f"牌局开始，庄位是 {button_seat_index + 1} 号座位")
            self._auto_play_bots(room)
            self._sync_actor_timer(room)
            self._touch(room)
            return room

    def award_training_chips(self, *, room_code: str, guest_id: str, amount: int = 5000) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            guest = self._require_member(room, guest_id)
            seat = room.seat_for_guest(guest_id)
            if seat is None:
                raise RoomServiceError("NOT_SITTED", "请先坐下再领取训练筹码")
            if amount != 5000:
                raise RoomServiceError("INVALID_TRAINING_CHIPS_AMOUNT", "每次只能领取 5000 训练筹码")
            if self._is_guest_in_active_hand(room, guest_id):
                raise RoomServiceError("HAND_IN_PROGRESS", "当前手牌进行中，不能领取训练筹码")
            if guest.chips > 0:
                raise RoomServiceError("TRAINING_CHIPS_NOT_ALLOWED", "只有输光后才能领取训练筹码")

            self._award_training_chips_to_guest(room, guest, amount=amount)
            self._touch(room)
            return room

    def borrow_chips(self, *, room_code: str, guest_id: str, amount: int = 5000) -> Room:
        return self.award_training_chips(room_code=room_code, guest_id=guest_id, amount=amount)

    def send_chat_message(self, *, room_code: str, guest_id: str, content: str) -> tuple[Room, ChatMessage]:
        with self._lock:
            room = self.get_room(room_code)
            guest = self._require_member(room, guest_id)
            normalized = content.strip()
            if not normalized:
                raise RoomServiceError("EMPTY_MESSAGE", "聊天内容不能为空")
            if len(normalized) > 200:
                raise RoomServiceError("MESSAGE_TOO_LONG", "聊天内容不能超过 200 字")

            message = self._append_chat_message(
                room,
                guest_id=guest.guest_id,
                nickname=guest.nickname,
                content=normalized,
                is_system=False,
            )
            self._touch(room)
            return room, message

    def set_ai_enabled(self, *, room_code: str, guest_id: str, is_enabled: bool) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            if room.host_guest_id != guest_id:
                raise RoomServiceError("NOT_HOST", "只有房主可以控制 AI 助手")
            room.ai_enabled_by_default = is_enabled
            self._append_event(
                room,
                "ai_enabled_changed",
                f"房主已{'开启' if is_enabled else '关闭'} AI 助手",
            )
            self._touch(room)
            return room

    def use_time_card(self, *, room_code: str, guest_id: str) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            guest = self._require_member(room, guest_id)
            if room.status != RoomStatus.PLAYING or room.current_game is None:
                raise RoomServiceError("GAME_NOT_RUNNING", "当前没有正在进行的牌局")
            if room.is_paused:
                raise RoomServiceError("GAME_PAUSED", "牌局已暂停")

            seat = room.seat_for_guest(guest_id)
            if seat is None or room.current_game.current_actor_seat_index != seat.seat_index:
                raise RoomServiceError("NOT_CURRENT_ACTOR", "只有当前行动玩家可以使用时间卡")
            if guest.time_cards_remaining <= 0:
                raise RoomServiceError("NO_TIME_CARDS", "时间卡已经用完")

            self._use_time_card_for_actor(room, guest, automatic=False)
            self._touch(room)
            return room

    def process_timeouts(self, *, room_code: str) -> Room | None:
        with self._lock:
            room = self.get_room(room_code)
            if self._process_timeouts_locked(room):
                return room
            return None

    def player_action(
        self,
        *,
        room_code: str,
        guest_id: str,
        action: str,
        amount: int = 0,
    ) -> Room:
        with self._lock:
            room = self.get_room(room_code)
            self._require_member(room, guest_id)
            if room.status != RoomStatus.PLAYING or room.current_game is None:
                raise RoomServiceError("GAME_NOT_RUNNING", "当前没有正在进行的牌局")
            if room.is_paused:
                raise RoomServiceError("GAME_PAUSED", "牌局已暂停")

            seat = room.seat_for_guest(guest_id)
            if seat is None:
                raise RoomServiceError("NOT_SITTED", "旁观者不能操作")
            if not self._is_seat_in_current_game(room, seat.seat_index):
                raise RoomServiceError("SPECTATOR_ONLY", "该座位正在等待下一局，当前不能操作")

            self._process_timeouts_locked(room)
            if room.status != RoomStatus.PLAYING or room.current_game is None:
                raise RoomServiceError("GAME_NOT_RUNNING", "当前没有正在进行的牌局")

            try:
                action_type = PlayerActionType(action)
                room.current_game.apply_action(seat.seat_index, action_type, amount=amount)
            except (ValueError, InvalidGameAction) as exc:
                raise RoomServiceError("INVALID_ACTION", str(exc)) from exc

            amount_suffix = f" 到 {amount}" if amount else ""
            self._append_event(
                room,
                "player_action",
                f"{room.members[guest_id].nickname}: {self._action_label(action_type)}{amount_suffix}",
            )

            if room.current_game.phase == BettingPhase.FINISHED:
                self._finish_current_hand(room)
            else:
                self._auto_play_bots(room)

            self._sync_actor_timer(room)
            self._touch(room)
            return room

    def serialize_room(self, room: Room, *, viewer_guest_id: str | None) -> RoomStateView:
        with self._lock:
            self._process_timeouts_locked(room)
            viewer_seat = room.seat_for_guest(viewer_guest_id) if viewer_guest_id else None
            viewer = ViewerView(
                guest_id=viewer_guest_id,
                seat_index=viewer_seat.seat_index if viewer_seat else None,
                is_host=viewer_guest_id == room.host_guest_id,
                can_act=self._viewer_can_act(room, viewer_seat),
                legal_actions=self._viewer_legal_actions(room, viewer_seat),
            )
            game = room.current_game
            phase = game.phase.value if game is not None else room.status.value
            action_expires_at = self._action_expires_at(room)
            return RoomStateView(
                room_id=room.room_id,
                room_code=room.room_code,
                status=room.status.value,
                phase=phase,
                revision=room.revision,
                ai_enabled_by_default=room.ai_enabled_by_default,
                is_paused=room.is_paused,
                ready_break_required=self._ready_break_required(room),
                hand_number=room.hand_number,
                player_count=len(game.seats) if game else sum(1 for seat in room.seats if seat.guest_id),
                host_guest_id=room.host_guest_id,
                small_blind=room.small_blind,
                big_blind=room.big_blind,
                button_seat_index=room.button_seat_index,
                small_blind_seat_index=game.small_blind_seat_index if game else None,
                big_blind_seat_index=game.big_blind_seat_index if game else None,
                current_actor_seat_index=game.current_actor_seat_index if game else None,
                current_bet=game.current_bet if game else 0,
                min_raise=game.min_raise if game else room.big_blind,
                pot_total=game.pot_total if game else 0,
                action_started_at=room.action_started_at.isoformat()
                if room.action_started_at
                else None,
                action_expires_at=action_expires_at.isoformat()
                if action_expires_at
                else None,
                action_timeout_seconds=room.action_timeout_seconds,
                community_cards=[str(card) for card in game.community_cards] if game else [],
                seats=[
                    self._serialize_seat(room, room_seat, viewer_guest_id=viewer_guest_id)
                    for room_seat in room.seats
                ],
                viewer=viewer,
                action_options=self._viewer_action_options(room, viewer_seat),
                ai_assistant=self._viewer_ai_assistant(room, viewer_seat),
                rankings=self._ranking_entries(room),
                event_log=[
                    RoomEventView(
                        id=event.id,
                        type=event.type,
                        message=event.message,
                        created_at=event.created_at.isoformat(),
                    )
                    for event in room.event_log[-80:]
                ],
                chat_messages=[
                    self.serialize_chat_message(message)
                    for message in room.chat_messages[-100:]
                ],
                last_result=self._serialize_result(game) if game else None,
            )

    def list_rooms(self) -> list[RoomSummaryView]:
        with self._lock:
            return [
                RoomSummaryView(
                    room_code=room.room_code,
                    status=room.status.value,
                    ai_enabled_by_default=room.ai_enabled_by_default,
                    occupied_seats=sum(1 for seat in room.seats if seat.guest_id),
                    member_count=len(room.members),
                    max_seats=room.max_seats,
                    small_blind=room.small_blind,
                    big_blind=room.big_blind,
                    host_nickname=room.members[room.host_guest_id].nickname
                    if room.host_guest_id in room.members
                    else "未知",
                    can_join=len(room.members) < room.max_members,
                )
                for room in sorted(
                    self._rooms_by_code.values(),
                    key=lambda current_room: current_room.updated_at,
                    reverse=True,
                )
            ][:20]

    def clear_rooms_created_on(self, target_date: date, *, timezone: tzinfo) -> list[Room]:
        with self._lock:
            removed_rooms: list[Room] = []
            for room_code, room in list(self._rooms_by_code.items()):
                if room.created_at.astimezone(timezone).date() == target_date:
                    removed_rooms.append(room)
                    del self._rooms_by_code[room_code]
            return removed_rooms

    def envelope_for(self, room: Room, guest: GuestUser) -> RoomEnvelope:
        return RoomEnvelope(
            guest=GuestSessionView(
                guest_id=guest.guest_id,
                nickname=guest.nickname,
                chips=guest.chips,
                training_chips_awarded=guest.training_chips_awarded,
                time_cards_remaining=guest.time_cards_remaining,
            ),
            room=self.serialize_room(room, viewer_guest_id=guest.guest_id),
        )

    def _build_guest(self, *, nickname: str, guest_id: str | None) -> GuestUser:
        normalized_nickname = self._session_service.normalize_nickname(nickname)
        if guest_id and guest_id in self._registered_users_by_id:
            registered = self._registered_users_by_id[guest_id]
            normalized_nickname = registered.nickname
        else:
            existing_registered = self._registered_users_by_name.get(
                self._nickname_key(normalized_nickname)
            )
            if existing_registered is not None and existing_registered.guest_id != guest_id:
                raise RoomServiceError("USER_ALREADY_EXISTS", "这个昵称已经注册，请先使用注册身份")
        return GuestUser(
            guest_id=guest_id or self._session_service.create_guest_id(),
            nickname=normalized_nickname,
            chips=self._session_service.initial_chips,
        )

    @staticmethod
    def _nickname_key(nickname: str) -> str:
        return nickname.casefold()

    def _generate_room_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        while True:
            room_code = "".join(random.choices(alphabet, k=6))
            if room_code not in self._rooms_by_code:
                return room_code

    def _require_member(self, room: Room, guest_id: str) -> GuestUser:
        try:
            guest = room.members[guest_id]
        except KeyError as exc:
            raise RoomServiceError("NOT_IN_ROOM", "用户不在这个房间") from exc
        guest.last_seen_at = datetime.now(UTC)
        return guest

    def _touch(self, room: Room) -> None:
        room.revision += 1
        room.updated_at = datetime.now(UTC)

    def _ready_player_profiles(self, room: Room) -> list[PlayerProfile]:
        profiles: list[PlayerProfile] = []
        for seat in room.seats:
            if not seat.guest_id or not seat.is_ready:
                continue
            guest = room.members[seat.guest_id]
            if guest.chips <= 0:
                continue
            profiles.append(
                PlayerProfile(
                    seat_index=seat.seat_index,
                    player_id=guest.guest_id,
                    nickname=guest.nickname,
                    chips=guest.chips,
                )
            )
        return profiles

    def _button_for_next_hand(
        self,
        room: Room,
        player_profiles: list[PlayerProfile],
    ) -> int:
        player_seats = [player.seat_index for player in player_profiles]
        if room.button_seat_index in player_seats:
            return room.button_seat_index
        if room.button_seat_index is None:
            return min(player_seats)
        return min(
            player_seats,
            key=lambda seat_index: (seat_index - room.button_seat_index - 1) % room.max_seats,
        )

    def _finish_current_hand(self, room: Room) -> None:
        if room.current_game is None:
            return

        for game_seat in room.current_game.seats:
            guest = room.members.get(game_seat.player_id)
            if guest is not None:
                guest.chips = game_seat.chips
                if guest.chips == 0:
                    self._award_training_chips_to_guest(room, guest, amount=5000)

        participating_seats = [seat.seat_index for seat in room.current_game.seats]
        room.status = RoomStatus.WAITING
        room.is_paused = False
        room.paused_by_guest_id = None
        room.action_started_at = None
        room.action_deadline_at = None
        room.button_seat_index = self._next_occupied_seat_after(
            room,
            room.button_seat_index,
            participating_seats,
        )
        if self._should_require_ready_break(room):
            for seat in room.seats:
                if seat.guest_id in {game_seat.player_id for game_seat in room.current_game.seats}:
                    member = room.members.get(seat.guest_id)
                    seat.is_ready = bool(member and member.is_bot)
            self._append_event(room, "ready_break", "已完成 20 手，请重新准备后继续")
        if room.current_game.result:
            winners = ", ".join(
                f"{winner.seat_index + 1} 号座位 +{winner.amount}"
                for winner in room.current_game.result.winners
            )
            self._append_event(room, "hand_finished", f"牌局结束：{winners}")

    def _should_require_ready_break(self, room: Room) -> bool:
        return room.hand_number > 0 and room.hand_number % 20 == 0

    def _ready_break_required(self, room: Room) -> bool:
        return (
            self._should_require_ready_break(room)
            and room.status == RoomStatus.WAITING
            and room.current_game is not None
            and room.current_game.phase == BettingPhase.FINISHED
        )

    def _all_eligible_seated_players_ready(self, room: Room) -> bool:
        for seat in room.seats:
            if not seat.guest_id:
                continue
            guest = room.members[seat.guest_id]
            if guest.chips > 0 and not seat.is_ready:
                return False
        return True

    def _next_occupied_seat_after(
        self,
        room: Room,
        seat_index: int | None,
        fallback_candidates: list[int],
    ) -> int | None:
        occupied = [
            seat.seat_index
            for seat in room.seats
            if seat.guest_id and room.members[seat.guest_id].chips > 0
        ]
        candidates = occupied or fallback_candidates
        if not candidates:
            return None
        if seat_index is None:
            return min(candidates)
        return min(
            candidates,
            key=lambda candidate: (candidate - seat_index - 1) % room.max_seats,
        )

    def _is_guest_in_active_hand(self, room: Room, guest_id: str) -> bool:
        if room.current_game is None or room.current_game.phase == BettingPhase.FINISHED:
            return False
        return any(game_seat.player_id == guest_id for game_seat in room.current_game.seats)

    def _is_seat_in_current_game(self, room: Room, seat_index: int) -> bool:
        if room.current_game is None:
            return False
        return any(game_seat.seat_index == seat_index for game_seat in room.current_game.seats)

    def _viewer_can_act(self, room: Room, viewer_seat: RoomSeat | None) -> bool:
        if room.is_paused or room.current_game is None or viewer_seat is None:
            return False
        return room.current_game.current_actor_seat_index == viewer_seat.seat_index

    def _viewer_legal_actions(self, room: Room, viewer_seat: RoomSeat | None) -> list[str]:
        if room.is_paused or room.current_game is None or viewer_seat is None:
            return []
        return [
            action.value
            for action in room.current_game.legal_actions_for(viewer_seat.seat_index)
        ]

    def _viewer_action_options(
        self,
        room: Room,
        viewer_seat: RoomSeat | None,
    ) -> ActionOptionsView:
        if room.is_paused or room.current_game is None or viewer_seat is None:
            return ActionOptionsView()

        game_seat = self._game_seat_by_index(room, viewer_seat.seat_index)
        if game_seat is None:
            return ActionOptionsView()

        actions = room.current_game.legal_action_details_for(viewer_seat.seat_index)
        to_call = max(0, room.current_game.current_bet - game_seat.current_bet)
        min_bet: int | None = None
        max_bet: int | None = None
        min_raise_to: int | None = None
        max_raise_to: int | None = None
        all_in_amount = game_seat.chips

        for action in actions:
            if action.action_type == PlayerActionType.CALL:
                to_call = action.call_amount
            elif action.action_type == PlayerActionType.BET:
                min_bet = action.min_amount
                max_bet = action.max_amount
            elif action.action_type == PlayerActionType.RAISE:
                min_raise_to = action.min_amount
                max_raise_to = action.max_amount
            elif action.action_type == PlayerActionType.ALL_IN:
                all_in_amount = game_seat.chips

        quick_bets = self._quick_bet_targets(
            game=room.current_game,
            game_seat=game_seat,
            min_bet=min_bet,
            max_bet=max_bet,
            min_raise_to=min_raise_to,
            max_raise_to=max_raise_to,
        )
        return ActionOptionsView(
            to_call=to_call,
            min_bet=min_bet,
            max_bet=max_bet,
            min_raise_to=min_raise_to,
            max_raise_to=max_raise_to,
            all_in_amount=all_in_amount,
            quick_bets=quick_bets,
        )

    def _quick_bet_targets(
        self,
        *,
        game: GameState,
        game_seat: GameSeatState,
        min_bet: int | None,
        max_bet: int | None,
        min_raise_to: int | None,
        max_raise_to: int | None,
    ) -> dict[str, int]:
        min_target = min_raise_to if min_raise_to is not None else min_bet
        max_target = max_raise_to if max_raise_to is not None else max_bet
        if min_target is None or max_target is None:
            return {}

        all_in_target = game_seat.current_bet + game_seat.chips
        targets = {
            "最小": min_target,
            "3BB": max(min_target, game.big_blind * 3),
            "4BB": max(min_target, game.big_blind * 4),
            "5BB": max(min_target, game.big_blind * 5),
            "全下": all_in_target,
        }
        return {
            label: min(max_target, target)
            for label, target in targets.items()
            if target >= min_target
        }

    def _process_timeouts_locked(self, room: Room) -> bool:
        if room.status != RoomStatus.PLAYING or room.is_paused or room.current_game is None:
            return False
        deadline = self._action_expires_at(room)
        if deadline is None or datetime.now(UTC) < deadline:
            return False

        actor = self._current_actor_member(room)
        if actor is None:
            self._sync_actor_timer(room)
            self._touch(room)
            return True

        game_seat, guest = actor
        if guest.time_cards_remaining > 0:
            self._use_time_card_for_actor(room, guest, automatic=True)
            self._touch(room)
            return True

        room.current_game.apply_action(game_seat.seat_index, PlayerActionType.FOLD)
        self._append_event(
            room,
            "auto_fold",
            f"{guest.nickname} 超时，时间卡已用完，自动弃牌",
        )
        if room.current_game.phase == BettingPhase.FINISHED:
            self._finish_current_hand(room)
        else:
            self._auto_play_bots(room)
        self._sync_actor_timer(room)
        self._touch(room)
        return True

    def _current_actor_member(self, room: Room) -> tuple[GameSeatState, GuestUser] | None:
        if room.current_game is None or room.current_game.current_actor_seat_index is None:
            return None
        game_seat = self._game_seat_by_index(room, room.current_game.current_actor_seat_index)
        if game_seat is None:
            return None
        guest = room.members.get(game_seat.player_id)
        if guest is None:
            return None
        return game_seat, guest

    def _use_time_card_for_actor(
        self,
        room: Room,
        guest: GuestUser,
        *,
        automatic: bool,
    ) -> None:
        now = datetime.now(UTC)
        base_deadline = room.action_deadline_at if room.action_deadline_at and room.action_deadline_at > now else now
        if room.action_started_at is None:
            room.action_started_at = now
        guest.time_cards_remaining = max(0, guest.time_cards_remaining - 1)
        room.action_deadline_at = base_deadline + timedelta(seconds=TIME_CARD_EXTENSION_SECONDS)
        event_message = (
            f"{guest.nickname} 超时，系统自动使用 1 张时间卡，剩余 {guest.time_cards_remaining} 张"
            if automatic
            else f"{guest.nickname} 使用 1 张时间卡，延长 {TIME_CARD_EXTENSION_SECONDS} 秒，剩余 {guest.time_cards_remaining} 张"
        )
        self._append_event(room, "time_card_used", event_message)

    def _action_expires_at(self, room: Room) -> datetime | None:
        if room.action_deadline_at is None:
            return None
        if room.status != RoomStatus.PLAYING or room.is_paused:
            return None
        if room.current_game is None or room.current_game.current_actor_seat_index is None:
            return None
        return room.action_deadline_at

    def _sync_actor_timer(self, room: Room) -> None:
        if (
            room.status == RoomStatus.PLAYING
            and not room.is_paused
            and room.current_game is not None
            and room.current_game.current_actor_seat_index is not None
        ):
            now = datetime.now(UTC)
            room.action_started_at = now
            room.action_deadline_at = now + timedelta(seconds=room.action_timeout_seconds)
            return
        room.action_started_at = None
        room.action_deadline_at = None

    def _position_label(self, game: GameState | None, seat_index: int) -> str | None:
        if game is None:
            return None
        game_seat_indexes = [seat.seat_index for seat in game.seats]
        if seat_index not in game_seat_indexes:
            return None

        labels: list[str] = []
        if seat_index == game.button_seat_index:
            labels.append("BTN")
        if seat_index == game.small_blind_seat_index:
            labels.append("SB")
        if seat_index == game.big_blind_seat_index:
            labels.append("BB")
        if labels:
            return "/".join(labels)

        position_base = (
            game.big_blind_seat_index
            if game.big_blind_seat_index is not None
            else game.button_seat_index
        )
        ordered_after_big_blind = sorted(
            (
                current
                for current in game_seat_indexes
                if current
                not in {
                    game.button_seat_index,
                    game.small_blind_seat_index,
                    game.big_blind_seat_index,
                }
            ),
            key=lambda current: (current - position_base - 1) % game.max_seats,
        )
        if seat_index not in ordered_after_big_blind:
            return None

        position_index = ordered_after_big_blind.index(seat_index)
        count = len(ordered_after_big_blind)
        if count == 1:
            labels_by_count = ["UTG"]
        elif count == 2:
            labels_by_count = ["UTG", "CO"]
        elif count == 3:
            labels_by_count = ["UTG", "MP", "CO"]
        elif count == 4:
            labels_by_count = ["UTG", "MP", "HJ", "CO"]
        else:
            middle_count = count - 3
            labels_by_count = ["UTG"]
            labels_by_count.extend(f"UTG+{index}" for index in range(1, middle_count))
            labels_by_count.extend(["MP", "HJ", "CO"])
        return labels_by_count[position_index]

    def _viewer_ai_assistant(
        self,
        room: Room,
        viewer_seat: RoomSeat | None,
    ) -> AiAssistantView:
        if not room.ai_enabled_by_default:
            return AiAssistantView(summary="AI 助手已由房主关闭。")
        if room.current_game is None or viewer_seat is None:
            return AiAssistantView(summary="坐下并参与牌局后，AI 助手会分析你的手牌。")

        game_seat = self._game_seat_by_index(room, viewer_seat.seat_index)
        if game_seat is None or not game_seat.hole_cards:
            return AiAssistantView(summary="当前座位未参与本局，等待下一局开始。")

        strength = self._bot_strength(room.current_game, game_seat)
        strength_percent = max(1, min(99, round(strength * 100)))
        range_rank = max(1, min(169, round((1 - strength) * 168) + 1))
        hand_label = self._hand_label(room.current_game, game_seat)
        grade = self._grade_for_strength(strength)
        win_rate_percent = round(max(3.0, min(96.0, strength * 100)), 1)
        summary = self._ai_summary(strength=strength, to_call=max(0, room.current_game.current_bet - game_seat.current_bet))
        return AiAssistantView(
            enabled=True,
            hand_label=hand_label,
            strength_percent=strength_percent,
            percentile_label=f"Top {max(1, min(99, round(range_rank / 169 * 100)))}%",
            rank_text=f"#{range_rank}/169",
            grade=grade,
            win_rate_percent=win_rate_percent,
            summary=summary,
            draw_notes=self._draw_notes(room.current_game, game_seat),
        )

    def _hand_label(self, game: GameState, game_seat: GameSeatState) -> str:
        cards = [*game_seat.hole_cards, *game.community_cards]
        if len(cards) >= 5:
            evaluation = HandEvaluator.evaluate(cards)
            return self._hand_category_label(evaluation.category)
        return self._preflop_hand_label(game_seat.hole_cards)

    def _preflop_hand_label(self, cards: list[Card]) -> str:
        if len(cards) < 2:
            return "等待手牌"
        left, right = sorted(cards, key=lambda card: int(card.rank), reverse=True)
        suited = left.suit == right.suit
        if left.rank == right.rank:
            return f"口袋对子 {left.rank.symbol}{right.rank.symbol}"
        suited_text = "同花" if suited else "杂色"
        return f"{suited_text} {left.rank.symbol}{right.rank.symbol}"

    def _hand_category_label(self, category: HandCategory) -> str:
        return {
            HandCategory.HIGH_CARD: "高牌",
            HandCategory.ONE_PAIR: "一对",
            HandCategory.TWO_PAIR: "两对",
            HandCategory.THREE_OF_A_KIND: "三条",
            HandCategory.STRAIGHT: "顺子",
            HandCategory.FLUSH: "同花",
            HandCategory.FULL_HOUSE: "葫芦",
            HandCategory.FOUR_OF_A_KIND: "四条",
            HandCategory.STRAIGHT_FLUSH: "同花顺",
            HandCategory.ROYAL_FLUSH: "皇家同花顺",
        }[category]

    def _grade_for_strength(self, strength: float) -> str:
        if strength >= 0.88:
            return "顶级强牌"
        if strength >= 0.72:
            return "强牌"
        if strength >= 0.55:
            return "可玩"
        if strength >= 0.38:
            return "边缘牌"
        return "弱牌"

    def _ai_summary(self, *, strength: float, to_call: int) -> str:
        if strength >= 0.82:
            return "当前牌力领先，面对常规下注可以主动加压。"
        if strength >= 0.62:
            return "牌力不错，适合跟注或小幅主动下注，避免无谓全下。"
        if to_call == 0:
            return "牌力一般，可以过牌控制底池。"
        if strength >= 0.42:
            return "牌力偏边缘，跟注前关注对手下注尺度。"
        return "牌力较弱，面对较大下注优先弃牌。"

    def _draw_notes(self, game: GameState, game_seat: GameSeatState) -> list[str]:
        cards = [*game_seat.hole_cards, *game.community_cards]
        if len(game.community_cards) < 3:
            return ["翻牌前估算", "公共牌出现后会更新成牌和听牌信息"]

        notes: list[str] = []
        suit_counts: dict[str, int] = {}
        for card in cards:
            suit_counts[card.suit.value] = suit_counts.get(card.suit.value, 0) + 1
        if any(count >= 5 for count in suit_counts.values()):
            notes.append("已经成同花或更好")
        elif any(count == 4 for count in suit_counts.values()):
            notes.append("同花听牌")

        ranks = sorted({int(card.rank) for card in cards})
        if 14 in ranks:
            ranks.insert(0, 1)
        straight_window = any(
            len(set(range(start, start + 5)).intersection(ranks)) >= 4
            for start in range(1, 11)
        )
        if straight_window:
            notes.append("顺子听牌")

        if not notes:
            notes.append("暂无明显听牌")
        return notes

    def _serialize_seat(
        self,
        room: Room,
        room_seat: RoomSeat,
        *,
        viewer_guest_id: str | None,
    ) -> SeatView:
        if room_seat.guest_id is None:
            return SeatView(seat_index=room_seat.seat_index, occupied=False)

        guest = room.members[room_seat.guest_id]
        game_seat = self._game_seat_by_index(room, room_seat.seat_index)
        return SeatView(
            seat_index=room_seat.seat_index,
            occupied=True,
            guest_id=guest.guest_id,
            nickname=guest.nickname,
            position_label=self._position_label(room.current_game, room_seat.seat_index)
            if room.current_game
            else None,
            chips=game_seat.chips if game_seat else guest.chips,
            training_chips_awarded=guest.training_chips_awarded,
            time_cards_remaining=guest.time_cards_remaining,
            current_bet=game_seat.current_bet if game_seat else 0,
            total_committed=game_seat.total_committed if game_seat else 0,
            has_folded=game_seat.has_folded if game_seat else False,
            is_all_in=game_seat.is_all_in if game_seat else False,
            is_current_actor=room.current_game.current_actor_seat_index == room_seat.seat_index
            if room.current_game
            else False,
            is_ready=room_seat.is_ready,
            is_connected=guest.is_connected,
            is_bot=guest.is_bot,
            last_action=game_seat.last_action.value if game_seat and game_seat.last_action else None,
            hole_cards=self._visible_hole_cards(
                room,
                game_seat,
                viewer_guest_id=viewer_guest_id,
            ),
        )

    def _ranking_entries(self, room: Room) -> list[RankingEntryView]:
        ranked_members: list[tuple[int, int, datetime, GuestUser, int | None, int, int]] = []
        for guest in room.members.values():
            seat = room.seat_for_guest(guest.guest_id)
            current_chips = self._current_member_chips(room, guest)
            buy_in_chips = self._session_service.initial_chips + guest.training_chips_awarded
            net_chips = current_chips - buy_in_chips
            ranked_members.append(
                (
                    net_chips,
                    current_chips,
                    guest.joined_at,
                    guest,
                    seat.seat_index if seat else None,
                    buy_in_chips,
                    guest.training_chips_awarded,
                )
            )

        ranked_members.sort(
            key=lambda item: (-item[0], -item[1], item[2], item[3].nickname.casefold())
        )

        entries: list[RankingEntryView] = []
        previous_score: tuple[int, int] | None = None
        current_rank = 0
        for index, item in enumerate(ranked_members, start=1):
            net_chips, current_chips, _, guest, seat_index, buy_in_chips, training_chips_awarded = item
            score = (net_chips, current_chips)
            if score != previous_score:
                current_rank = index
                previous_score = score
            entries.append(
                RankingEntryView(
                    rank=current_rank,
                    guest_id=guest.guest_id,
                    nickname=guest.nickname,
                    seat_index=seat_index,
                    is_bot=guest.is_bot,
                    current_chips=current_chips,
                    buy_in_chips=buy_in_chips,
                    training_chips_awarded=training_chips_awarded,
                    net_chips=net_chips,
                )
            )
        return entries

    def _current_member_chips(self, room: Room, guest: GuestUser) -> int:
        if room.current_game is None:
            return guest.chips

        for game_seat in room.current_game.seats:
            if game_seat.player_id == guest.guest_id:
                return game_seat.chips + game_seat.total_committed
        return guest.chips

    def serialize_chat_message(self, message: ChatMessage) -> ChatMessageView:
        return ChatMessageView(
            message_id=message.message_id,
            room_code=message.room_code,
            guest_id=message.guest_id,
            nickname=message.nickname,
            content=message.content,
            created_at=message.created_at.isoformat(),
            is_system=message.is_system,
        )

    def _game_seat_by_index(self, room: Room, seat_index: int) -> GameSeatState | None:
        if room.current_game is None:
            return None
        for game_seat in room.current_game.seats:
            if game_seat.seat_index == seat_index:
                return game_seat
        return None

    def _visible_hole_cards(
        self,
        room: Room,
        game_seat: GameSeatState | None,
        *,
        viewer_guest_id: str | None,
    ) -> list[str]:
        if room.current_game is None or game_seat is None:
            return []

        seat_player_id = game_seat.player_id
        hole_cards = game_seat.hole_cards
        if viewer_guest_id == seat_player_id:
            return [str(card) for card in hole_cards]

        result = room.current_game.result
        if result and any(hand.seat_index == game_seat.seat_index for hand in result.showdown_hands):
            return [str(card) for card in hole_cards]

        if room.current_game.phase != BettingPhase.FINISHED:
            return ["hidden", "hidden"]
        return []

    def _serialize_result(self, game: GameState | None) -> HandResultView | None:
        if game is None or game.result is None:
            return None

        return HandResultView(
            winners=[
                WinnerView(
                    seat_index=winner.seat_index,
                    amount=winner.amount,
                    hand_category_name=winner.hand_category_name,
                )
                for winner in game.result.winners
            ],
            pot_distributions=[
                PotDistributionView(
                    pot_index=distribution.pot_index,
                    amount=distribution.amount,
                    eligible_seat_indexes=list(distribution.eligible_seat_indexes),
                    winner_seat_indexes=list(distribution.winner_seat_indexes),
                    shares=[
                        PotShareView(seat_index=share.seat_index, amount=share.amount)
                        for share in distribution.shares
                    ],
                )
                for distribution in game.result.pot_distributions
            ],
            showdown_hands=[
                ShowdownHandView(
                    seat_index=hand.seat_index,
                    category_name=hand.evaluation.category_name,
                    best_cards=[str(card) for card in hand.evaluation.cards],
                )
                for hand in game.result.showdown_hands
            ],
        )

    def _append_event(self, room: Room, event_type: str, message: str) -> None:
        next_id = room.event_log[-1].id + 1 if room.event_log else 1
        room.event_log.append(RoomEvent(id=next_id, type=event_type, message=message))
        if len(room.event_log) > 120:
            del room.event_log[:-120]
        if event_type in {
            "room_created",
            "player_joined",
            "player_reconnected",
            "seat_taken",
            "stand_up",
            "player_left",
            "bot_added",
            "training_chips_awarded",
            "hand_started",
            "hand_finished",
            "ready_break",
            "ai_enabled_changed",
            "game_paused",
            "game_resumed",
            "game_ended",
            "time_card_used",
            "auto_fold",
        }:
            self._append_chat_message(
                room,
                guest_id=None,
                nickname="系统",
                content=message,
                is_system=True,
            )

    def _append_chat_message(
        self,
        room: Room,
        *,
        guest_id: str | None,
        nickname: str,
        content: str,
        is_system: bool,
    ) -> ChatMessage:
        next_id = room.chat_messages[-1].message_id + 1 if room.chat_messages else 1
        message = ChatMessage(
            message_id=next_id,
            room_code=room.room_code,
            guest_id=guest_id,
            nickname=nickname,
            content=content,
            is_system=is_system,
        )
        room.chat_messages.append(message)
        if len(room.chat_messages) > 100:
            del room.chat_messages[:-100]
        return message

    def _award_training_chips_to_guest(
        self,
        room: Room,
        guest: GuestUser,
        *,
        amount: int,
    ) -> None:
        guest.chips += amount
        guest.training_chips_awarded += amount
        self._append_event(
            room,
            "training_chips_awarded",
            f"{guest.nickname} 输光后获得 {amount} 训练筹码",
        )

    def _auto_play_bots(self, room: Room) -> None:
        if room.current_game is None:
            return

        for _ in range(100):
            game = room.current_game
            if room.status != RoomStatus.PLAYING or room.is_paused or game.phase == BettingPhase.FINISHED:
                break
            actor_index = game.current_actor_seat_index
            if actor_index is None:
                break

            game_seat = self._game_seat_by_index(room, actor_index)
            if game_seat is None:
                break
            bot = room.members.get(game_seat.player_id)
            if bot is None or not bot.is_bot:
                break

            action_type, amount = self._choose_bot_action(game, game_seat)
            game.apply_action(actor_index, action_type, amount=amount)
            amount_suffix = f" 到 {amount}" if amount else ""
            self._append_event(
                room,
                "bot_action",
                f"{bot.nickname}: {self._action_label(action_type)}{amount_suffix}",
            )

            if game.phase == BettingPhase.FINISHED:
                self._finish_current_hand(room)
                break

    def _choose_bot_action(
        self,
        game: GameState,
        seat: GameSeatState,
    ) -> tuple[PlayerActionType, int]:
        legal = set(game.legal_actions_for(seat.seat_index))
        strength = self._bot_strength(game, seat)

        if PlayerActionType.RAISE in legal and strength >= 0.82:
            target = min(seat.current_bet + seat.chips, game.current_bet + game.min_raise)
            if target > game.current_bet:
                return PlayerActionType.RAISE, target

        if PlayerActionType.BET in legal:
            if strength >= 0.68:
                target = min(seat.current_bet + seat.chips, max(game.big_blind, game.big_blind * 2))
                return PlayerActionType.BET, target
            return PlayerActionType.CHECK, 0

        if PlayerActionType.CHECK in legal:
            return PlayerActionType.CHECK, 0

        if PlayerActionType.CALL in legal:
            to_call = max(0, game.current_bet - seat.current_bet)
            pressure = to_call / max(1, seat.chips + seat.current_bet)
            if strength >= 0.62 or pressure <= 0.16:
                return PlayerActionType.CALL, 0
            if PlayerActionType.FOLD in legal:
                return PlayerActionType.FOLD, 0

        if PlayerActionType.ALL_IN in legal and strength >= 0.9:
            return PlayerActionType.ALL_IN, 0

        if PlayerActionType.FOLD in legal:
            return PlayerActionType.FOLD, 0

        return PlayerActionType.CHECK, 0

    def _bot_strength(self, game: GameState, seat: GameSeatState) -> float:
        hole_ranks = sorted((int(card.rank) for card in seat.hole_cards), reverse=True)
        if len(game.community_cards) >= 3:
            evaluation = HandEvaluator.evaluate([*seat.hole_cards, *game.community_cards])
            category_scores = {
                HandCategory.HIGH_CARD: 0.25,
                HandCategory.ONE_PAIR: 0.48,
                HandCategory.TWO_PAIR: 0.68,
                HandCategory.THREE_OF_A_KIND: 0.76,
                HandCategory.STRAIGHT: 0.82,
                HandCategory.FLUSH: 0.84,
                HandCategory.FULL_HOUSE: 0.92,
                HandCategory.FOUR_OF_A_KIND: 0.97,
                HandCategory.STRAIGHT_FLUSH: 0.99,
                HandCategory.ROYAL_FLUSH: 1.0,
            }
            kicker_bonus = min(0.08, sum(evaluation.ranks[:2]) / 350)
            return min(1.0, category_scores[evaluation.category] + kicker_bonus)

        if len(hole_ranks) < 2:
            return 0.3
        high, low = hole_ranks
        if high == low:
            return 0.62 + high / 40
        connected_bonus = 0.08 if abs(high - low) <= 1 else 0
        high_card_score = (high + low) / 32
        return min(0.86, high_card_score + connected_bonus)

    def _action_label(self, action_type: PlayerActionType) -> str:
        return {
            PlayerActionType.FOLD: "弃牌",
            PlayerActionType.CHECK: "过牌",
            PlayerActionType.CALL: "跟注",
            PlayerActionType.BET: "下注",
            PlayerActionType.RAISE: "加注",
            PlayerActionType.ALL_IN: "全下",
        }[action_type]
