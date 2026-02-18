import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # GitHub Copilot SDK
    COPILOT_GITHUB_TOKEN: str
    COPILOT_MODEL: str = "claude-3.5-sonnet"
    COPILOT_EVOLUTION_MODEL: str = "claude-3.5-sonnet" # Model specifically for self-evolution tasks
    GITHUB_REPO_NAME: Optional[str] = None # e.g. "owner/repo"

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Server Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Logging
    LOG_LEVEL: str = "INFO"

    # Session Management
    SESSION_MAX_TURNS: int = 10
    SESSION_TIMEOUT_MINUTES: int = 30
    SESSION_STORAGE_PATH: str = "storage"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
