"""
Application configuration loaded from environment variables.
Uses pydantic-settings for type-safe settings management.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised application settings derived from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_DEBUG: bool = True
    APP_SECRET_KEY: str = "change-me-in-production"

    # OpenAI / LangChain
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-3.5-turbo"
    OPENAI_MAX_TOKENS: int = 1024
    OPENAI_TEMPERATURE: float = 0.3

    # LangChain
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./support_dev.db"

    # Classification
    CONFIDENCE_THRESHOLD: float = 0.75

    # Analytics demo: simulated response times (seconds)
    MANUAL_RESPONSE_TIME_SECONDS: int = 720   # ~12 minutes
    AI_RESPONSE_TIME_SECONDS: int = 180       # ~3 minutes


settings = Settings()
