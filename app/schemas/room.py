from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.game import HandResultView


class CreateRoomRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    guest_id: str | None = None
    small_blind: int = Field(default=50, ge=1)
    big_blind: int = Field(default=100, ge=1)
    ai_enabled_by_default: bool = False


class JoinRoomRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=24)
    guest_id: str | None = None


class LeaveRoomRequest(BaseModel):
    guest_id: str


class AddBotRequest(BaseModel):
    guest_id: str


class TrainingChipsRequest(BaseModel):
    guest_id: str
    amount: int = Field(default=5000, ge=1)


class PauseGameRequest(BaseModel):
    guest_id: str
    is_paused: bool


class SitDownRequest(BaseModel):
    guest_id: str
    seat_index: int = Field(ge=0, le=19)


class ReadyRequest(BaseModel):
    guest_id: str
    is_ready: bool


class PlayerActionRequest(BaseModel):
    guest_id: str
    action: str
    amount: int = Field(default=0, ge=0)


class TimeCardRequest(BaseModel):
    guest_id: str


class SendChatMessageRequest(BaseModel):
    guest_id: str
    content: str = Field(min_length=1, max_length=200)


class GuestSessionView(BaseModel):
    guest_id: str
    nickname: str
    chips: int
    training_chips_awarded: int = 0
    time_cards_remaining: int = 5


class ActionOptionsView(BaseModel):
    to_call: int = 0
    min_bet: int | None = None
    max_bet: int | None = None
    min_raise_to: int | None = None
    max_raise_to: int | None = None
    all_in_amount: int = 0
    quick_bets: dict[str, int] = Field(default_factory=dict)


class AiAssistantView(BaseModel):
    enabled: bool = False
    hand_label: str = ""
    strength_percent: int = 0
    percentile_label: str = ""
    rank_text: str = ""
    grade: str = ""
    win_rate_percent: float = 0
    summary: str = ""
    draw_notes: list[str] = Field(default_factory=list)


class SeatView(BaseModel):
    seat_index: int
    occupied: bool
    guest_id: str | None = None
    nickname: str | None = None
    position_label: str | None = None
    is_bot: bool = False
    chips: int = 0
    training_chips_awarded: int = 0
    time_cards_remaining: int = 0
    current_bet: int = 0
    total_committed: int = 0
    has_folded: bool = False
    is_all_in: bool = False
    is_current_actor: bool = False
    is_ready: bool = False
    is_connected: bool = False
    last_action: str | None = None
    hole_cards: list[str] = Field(default_factory=list)


class RoomEventView(BaseModel):
    id: int
    type: str
    message: str
    created_at: str


class ChatMessageView(BaseModel):
    message_id: int
    room_code: str
    guest_id: str | None = None
    nickname: str
    content: str
    created_at: str
    is_system: bool = False


class ViewerView(BaseModel):
    guest_id: str | None
    seat_index: int | None
    is_host: bool = False
    can_act: bool = False
    legal_actions: list[str] = Field(default_factory=list)


class RoomStateView(BaseModel):
    room_id: str
    room_code: str
    status: str
    phase: str
    revision: int
    ai_enabled_by_default: bool = False
    is_paused: bool = False
    ready_break_required: bool = False
    hand_number: int = 0
    player_count: int = 0
    host_guest_id: str
    small_blind: int
    big_blind: int
    button_seat_index: int | None
    small_blind_seat_index: int | None = None
    big_blind_seat_index: int | None = None
    current_actor_seat_index: int | None = None
    current_bet: int = 0
    min_raise: int = 0
    pot_total: int = 0
    action_started_at: str | None = None
    action_expires_at: str | None = None
    action_timeout_seconds: int = 30
    community_cards: list[str] = Field(default_factory=list)
    seats: list[SeatView]
    viewer: ViewerView
    action_options: ActionOptionsView = Field(default_factory=ActionOptionsView)
    ai_assistant: AiAssistantView = Field(default_factory=AiAssistantView)
    event_log: list[RoomEventView] = Field(default_factory=list)
    chat_messages: list[ChatMessageView] = Field(default_factory=list)
    last_result: HandResultView | None = None


class RoomEnvelope(BaseModel):
    guest: GuestSessionView
    room: RoomStateView


class RoomSummaryView(BaseModel):
    room_code: str
    status: str
    ai_enabled_by_default: bool = False
    occupied_seats: int
    member_count: int
    max_seats: int
    small_blind: int
    big_blind: int
    host_nickname: str
    can_join: bool
