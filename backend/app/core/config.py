from functools import lru_cache
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_SECRET = "change-me"  # noqa: S105  (sentinel rejected in production)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Onezae Health API"
    APP_VERSION: str = "0.2.0"
    ENVIRONMENT: Literal["local", "test", "staging", "production"] = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:5173"

    # Security
    SECRET_KEY: str = _INSECURE_SECRET
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    REFRESH_COOKIE_NAME: str = "refresh_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30

    # Database: MySQL 8 (mysql+aiomysql://user:pass@host:3306/db?charset=utf8mb4).
    # SQLite is only a zero-setup fallback for quick local runs and tests.
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE_SECONDS: int = 1800  # keep below MySQL wait_timeout

    # HTTP
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    ALLOWED_HOSTS: Annotated[list[str], NoDecode] = ["*"]

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    # Clinic & scheduling. Schedules are wall-clock times in CLINIC_TIMEZONE;
    # every instant is stored in UTC.
    CLINIC_TIMEZONE: str = "Asia/Kolkata"
    APPOINTMENT_DURATION_MINUTES: int = 30
    BOOKING_MIN_LEAD_MINUTES: int = 60
    BOOKING_WINDOW_DAYS: int = 60
    CANCELLATION_CUTOFF_HOURS: int = 2
    REMINDER_LEAD_HOURS: int = 24

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Rate limits as "<requests>/<seconds>"; per client IP (auth) or per user.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH: str = "10/60"
    RATE_LIMIT_AI: str = "20/300"
    RATE_LIMIT_UPLOAD: str = "30/300"

    # Uploads (Cloudinary). The API secret never leaves the backend.
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: SecretStr = SecretStr("")
    CLOUDINARY_FOLDER: str = "onezae"
    UPLOAD_MAX_BYTES: int = 5 * 1024 * 1024
    UPLOAD_ALLOWED_IMAGE_TYPES: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]

    # AI assistant: Groq (OpenAI-compatible chat completions with tool calling)
    GROQ_API_KEY: SecretStr = SecretStr("")
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    AI_TEMPERATURE: float = 0.2
    AI_MAX_ITERATIONS: int = 6
    AI_MAX_TOKENS: int = 12_000
    AI_TIMEOUT_SECONDS: float = 45.0
    AI_MAX_INPUT_CHARS: int = 2_000
    AI_HISTORY_MESSAGES: int = 10
    AI_MAX_RECOMMENDED_DOCTORS: int = 3
    EMERGENCY_PHONE_NUMBER: str = "112"

    # Email. "console" logs a notice without secrets; plug a real provider in later.
    EMAIL_BACKEND: Literal["console", "disabled"] = "console"
    EMAIL_FROM: str = "no-reply@onezae.local"

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", "UPLOAD_ALLOWED_IMAGE_TYPES", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("CLINIC_TIMEZONE")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @field_validator("APPOINTMENT_DURATION_MINUTES")
    @classmethod
    def _valid_duration(cls, value: int) -> int:
        if not 5 <= value <= 240 or 1440 % value:
            raise ValueError("APPOINTMENT_DURATION_MINUTES must divide a day and be 5-240")
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production

    @property
    def clinic_tz(self) -> ZoneInfo:
        return ZoneInfo(self.CLINIC_TIMEZONE)

    @property
    def cloudinary_configured(self) -> bool:
        return bool(
            self.CLOUDINARY_CLOUD_NAME
            and self.CLOUDINARY_API_KEY
            and self.CLOUDINARY_API_SECRET.get_secret_value()
        )

    @property
    def ai_configured(self) -> bool:
        return bool(self.GROQ_API_KEY.get_secret_value())

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if not self.is_production:
            return self
        if self.SECRET_KEY == _INSECURE_SECRET or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be set to a random value of at least 32 chars")
        if self.DEBUG:
            raise ValueError("DEBUG must be false in production")
        if not self.COOKIE_SECURE:
            raise ValueError("COOKIE_SECURE must be true in production")
        if "*" in self.CORS_ORIGINS:
            raise ValueError("CORS_ORIGINS cannot contain '*' when credentials are allowed")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
