from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AssistantSettings(BaseSettings):
    """Backend-only configuration loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )

    assistant_provider: str = Field(
        default='deterministic',
        validation_alias='ASSISTANT_PROVIDER',
    )
    assistant_api_key: SecretStr | None = Field(
        default=None,
        validation_alias='ASSISTANT_API_KEY',
    )
    assistant_base_url: str | None = Field(
        default=None,
        validation_alias='ASSISTANT_BASE_URL',
    )
    assistant_model: str | None = Field(
        default=None,
        validation_alias='ASSISTANT_MODEL',
    )
    django_base_url: str = Field(
        default='http://127.0.0.1:8001',
        validation_alias='DJANGO_BASE_URL',
    )

    def require_api_key(self) -> str:
        if self.assistant_api_key is None:
            raise RuntimeError('ASSISTANT_API_KEY is not configured in the project .env file.')
        value = self.assistant_api_key.get_secret_value().strip()
        if not value:
            raise RuntimeError('ASSISTANT_API_KEY is not configured in the project .env file.')
        return value


@lru_cache
def get_assistant_settings() -> AssistantSettings:
    return AssistantSettings()
