from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    # Retry policy for transient OpenAI failures (429 / 5xx / network errors).
    openai_max_retries: int = Field(default=3, alias="OPENAI_MAX_RETRIES", ge=1, le=10)
    openai_retry_backoff: float = Field(
        default=1.5, alias="OPENAI_RETRY_BACKOFF", gt=0
    )

    # Empty value keeps the in-memory FSM storage (development mode).
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    prompts_dir: Path = Field(default=Path("prompts"), alias="PROMPTS_DIR")

    admin_user_id: int | None = Field(default=None, alias="ADMIN_USER_ID")

    active_topic_id: str | None = Field(default=None, alias="ACTIVE_TOPIC")

    quiz_question_count: int = Field(default=5, alias="QUIZ_QUESTION_COUNT", ge=1, le=20)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
