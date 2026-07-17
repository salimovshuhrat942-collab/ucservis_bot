from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Bot
    BOT_TOKEN: str
    BOT_USERNAME: str = ""

    # Access
    OWNER_ID: int
    ADMIN_IDS: str = ""

    # DB
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/bot.db"

    # Admin panel
    ADMIN_PANEL_SECRET: str = "insecure-dev-secret"
    ADMIN_PANEL_PASSWORD: str = "admin"
    ADMIN_PANEL_PORT: int = 8000

    # Storage
    TEMP_DIR: str = "./storage/temp"
    MAX_UPLOAD_MB: int = 200
    MAX_UPLOAD_MB_PREMIUM: int = 2000
    MAX_DURATION_SEC: int = 600

    # Queue
    QUEUE_WORKERS: int = 2
    QUEUE_WORKERS_PREMIUM: int = 2

    # Referral
    REFERRAL_REWARD_CONVERSIONS: int = 1

    # FFmpeg
    FFMPEG_PRESET: str = "veryfast"
    FFMPEG_THREADS: int = 2

    DEFAULT_LANGUAGE: str = "uz"

    @property
    def admin_ids(self) -> set[int]:
        ids = {self.OWNER_ID}
        for part in self.ADMIN_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    @property
    def temp_dir_path(self) -> Path:
        p = Path(self.TEMP_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
Path("./data").mkdir(parents=True, exist_ok=True)
settings.temp_dir_path
