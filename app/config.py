from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "德州扑克联机 MVP"
    guest_initial_chips: int = 10_000
    room_max_members: int = 20
    room_max_seats: int = 20
    default_small_blind: int = 50
    default_big_blind: int = 100
    database_url: str = "postgresql+psycopg://postgres:postgres@postgres:5432/holdem"
    redis_url: str = "redis://redis:6379/0"
    init_db: bool = False
    init_db_retries: int = 20
    init_db_retry_seconds: float = 1.0
    daily_room_cleanup_enabled: bool = True
    daily_room_cleanup_timezone: str = "Asia/Shanghai"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="HOLDEM_")


settings = Settings()
