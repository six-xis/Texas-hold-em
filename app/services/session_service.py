from __future__ import annotations

from uuid import uuid4


class SessionService:
    def __init__(self, *, initial_chips: int = 10_000) -> None:
        self.initial_chips = initial_chips

    def create_guest_id(self) -> str:
        return f"guest_{uuid4().hex}"

    def normalize_nickname(self, nickname: str) -> str:
        normalized = " ".join(nickname.strip().split())
        if not normalized:
            raise ValueError("请输入昵称")
        return normalized[:24]
