from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MP_", env_file=".env", extra="ignore")

    app_name: str = "MusicPilot"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    admin_username: str = "admin"
    admin_password: str = "musicpilot"
    session_secret: str = "musicpilot-dev-session-secret"
    database_url: str = "sqlite+aiosqlite:///./data/musicpilot.db"
    music_library_path: Path = Field(default=Path("./data/library"))
    download_staging_path: Path = Field(default=Path("./data/downloads"))
    static_dir: Path = Field(default=Path("frontend/dist"))
    system_indexer_parser_config: Path = Field(default=Path("config/sites.parser.yaml"))
    indexer_parser_config: Path = Field(default=Path("config/sites.parser.yaml"))
    runtime_config: Path = Field(default=Path("config/runtime.json"))
    qbittorrent_base_url: str | None = None
    qbittorrent_username: str | None = None
    qbittorrent_password: str | None = None
    navidrome_base_url: str | None = None
    navidrome_username: str | None = None
    navidrome_password: str | None = None
    navidrome_token: str | None = None
    musicbrainz_user_agent: str = "MusicPilot/0.1.0 (https://github.com/selfhosted/musicpilot)"
    write_audio_tags: bool = True
    telegram_bot_token: str | None = None
    telegram_chat_ids: str = ""
    subscriptions_enabled: bool = True
    subscription_check_interval_minutes: int = 1440
