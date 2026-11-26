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
    django_session_cookie_name: str = Field(
        default='sessionid',
        validation_alias='DJANGO_SESSION_COOKIE_NAME',
    )
    django_csrf_cookie_name: str = Field(
        default='csrftoken',
        validation_alias='DJANGO_CSRF_COOKIE_NAME',
    )
    pi_agent_base_url: str = Field(
        default='http://127.0.0.1:8010',
        validation_alias='PI_AGENT_BASE_URL',
    )
    pi_agent_service_token: SecretStr | None = Field(
        default=None,
        validation_alias='PI_AGENT_SERVICE_TOKEN',
    )
    tool_broker_base_url: str = Field(
        default='http://host.docker.internal:8002',
        validation_alias='TOOL_BROKER_BASE_URL',
    )
    agent_run_ttl_seconds: float = Field(
        default=120.0,
        gt=0,
        validation_alias='AGENT_RUN_TTL_SECONDS',
    )
    agent_run_timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        validation_alias='AGENT_RUN_TIMEOUT_SECONDS',
    )

    def require_api_key(self) -> str:
        if self.assistant_api_key is None:
            raise RuntimeError('ASSISTANT_API_KEY is not configured in the project .env file.')
        value = self.assistant_api_key.get_secret_value().strip()
        if not value:
            raise RuntimeError('ASSISTANT_API_KEY is not configured in the project .env file.')
        return value

    def require_pi_service_token(self) -> str:
        if self.pi_agent_service_token is None:
            raise RuntimeError('PI_AGENT_SERVICE_TOKEN is not configured.')
        value = self.pi_agent_service_token.get_secret_value().strip()
        if not value:
            raise RuntimeError('PI_AGENT_SERVICE_TOKEN is not configured.')
        return value


@lru_cache
def get_assistant_settings() -> AssistantSettings:
    return AssistantSettings()
