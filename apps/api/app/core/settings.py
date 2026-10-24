from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]  # apps/api in a checkout, /app in the image
# the monorepo root in a checkout; "/" in the image, where data is mounted at /data
REPO_ROOT = API_ROOT.parent.parent

# Dev-only fallbacks so `just dev` works on a fresh clone. Boot refuses them in prod.
_DEV_JWT = "dev-only-jwt-secret-change-me-0123456789abcdef"
_DEV_FERNET = "ZGV2LW9ubHktZW5jcnlwdGlvbi1rZXktMzJieXRlcyE="
_DEV_HASH = "dev-only-hash-key-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(REPO_ROOT / ".env", ".env"), extra="ignore", env_file_encoding="utf-8")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    public_base_url: str = "http://localhost:3100"
    cors_origins: list[str] = ["http://localhost:3100"]
    data_dir: Path = REPO_ROOT / "data"

    database_url: str = "postgresql+asyncpg://rescuegrid:rescuegrid@localhost:5432/rescuegrid"
    redis_url: str = "redis://localhost:6379/0"

    # understanding: "local" never sends text off the machine
    llm_provider: Literal["local", "gemini", "ollama"] = "local"
    llm_model: str = ""
    embed_model: str = ""
    gemini_api_key: SecretStr | None = None
    ollama_host: str = "http://localhost:11434"
    llm_timeout_s: float = 25.0
    llm_max_rpm: int = 12

    # geocoding: the gazetteer always runs; these are fallbacks
    nominatim_url: str = ""
    google_maps_api_key: SecretStr | None = None
    location_review_threshold: float = 0.6

    # routing: "estimate" is a flood-aware travel model with no external service
    router: Literal["estimate", "valhalla", "osrm"] = "estimate"
    router_url: str = ""
    dispatch_time_limit_s: float = 3.0
    dispatch_debounce_s: float = 5.0

    # whatsapp cloud api; outbound is skipped unless all of these are set
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: SecretStr | None = None
    whatsapp_verify_token: SecretStr | None = None
    whatsapp_app_secret: SecretStr | None = None
    whatsapp_api_version: str = "v23.0"

    # web push for field leads
    vapid_public_key: str = ""
    vapid_private_key: SecretStr | None = None
    vapid_subject: str = "mailto:ops@rescuegrid.local"

    jwt_secret: SecretStr = SecretStr(_DEV_JWT)
    jwt_expires_min: int = 30
    staff_session_hours: int = 12
    field_session_days: int = 7
    cookie_secure: bool = False
    cookie_domain: str | None = None

    # MultiFernet: first key encrypts, all keys decrypt (rotation)
    data_encryption_keys: SecretStr = SecretStr(_DEV_FERNET)
    data_hash_key: SecretStr = SecretStr(_DEV_HASH)
    retention_days: int = 90

    otp_dev_echo: bool = False
    demo_mode: bool = False
    workers_inline: bool = False
    nowcast_threads: int = 4  # flood ensemble members simulated at once by the workers
    sentry_dsn: str = ""

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, url: str) -> str:
        """Hosted Postgres hands out libpq URLs; asyncpg needs its own scheme and spells sslmode as ssl."""
        parts = urlsplit(url)
        if parts.scheme in ("postgres", "postgresql"):
            parts = parts._replace(scheme="postgresql+asyncpg")
        query = [("ssl" if k == "sslmode" else k, v) for k, v in parse_qsl(parts.query) if k != "channel_binding"]
        return urlunsplit(parts._replace(query=urlencode(query)))

    @model_validator(mode="after")
    def _refuse_dev_secrets_in_prod(self) -> Settings:
        if self.env != "prod":
            return self
        dev = {
            "JWT_SECRET": self.jwt_secret.get_secret_value() == _DEV_JWT,
            "DATA_ENCRYPTION_KEYS": self.data_encryption_keys.get_secret_value() == _DEV_FERNET,
            "DATA_HASH_KEY": self.data_hash_key.get_secret_value() == _DEV_HASH,
        }
        if bad := [k for k, v in dev.items() if v]:
            raise ValueError(f"dev secrets in prod: set {', '.join(bad)}")
        if self.otp_dev_echo:
            raise ValueError("OTP_DEV_ECHO must be off in prod")
        return self

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_phone_number_id and self.whatsapp_access_token and self.whatsapp_app_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
