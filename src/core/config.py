"""
Application Configuration
-------------------------
Uses Pydantic Settings for type-safe, validated configuration.
All secrets come from environment variables - never hardcoded.

Why Pydantic Settings?
- Automatic type coercion (str "5" -> int 5)
- Validation at startup (fail fast, not at 3 AM)
- Clear error messages for missing/invalid config
- Environment variable precedence over defaults
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Hierarchy (highest precedence first):
    1. Environment variables
    2. .env file
    3. Default values
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars
    )
    
    # ─────────────────────────────────────────────────────────────
    # Application
    # ─────────────────────────────────────────────────────────────
    app_name: str = "Kinmel Inventory"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    frontend_base_url: str | None = Field(default=None)
    
    # ─────────────────────────────────────────────────────────────
    # API Configuration
    # ─────────────────────────────────────────────────────────────
    api_v1_prefix: str = "/api/v1"
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
        ]
    )
    
    # ─────────────────────────────────────────────────────────────
    # Database (SQLite)
    # ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./kinmel.db"
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_pool_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_timeout: int = Field(default=30, ge=10, le=120)
    
    # ─────────────────────────────────────────────────────────────
    # Redis (Cache + Celery Broker)
    # ─────────────────────────────────────────────────────────────
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_cache_ttl: int = Field(default=300, ge=60, le=3600)  # 5 min default
    
    # ─────────────────────────────────────────────────────────────
    # Security
    # ─────────────────────────────────────────────────────────────
    secret_key: str = Field(
        default="CHANGE-ME-IN-PRODUCTION-USE-SECRETS-MANAGER",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=30)
    
    # Password hashing
    password_min_length: int = Field(default=8, ge=8, le=128)
    bcrypt_rounds: int = Field(default=12, ge=10, le=14)
    
    # ─────────────────────────────────────────────────────────────
    # Rate Limiting (staff-proof: prevent accidental spam)
    # ─────────────────────────────────────────────────────────────
    rate_limit_requests_per_minute: int = Field(default=60, ge=10, le=1000)
    
    # ─────────────────────────────────────────────────────────────
    # Inventory-Specific Settings
    # ─────────────────────────────────────────────────────────────
    low_stock_threshold_percent: int = Field(default=20, ge=5, le=50)
    expiry_warning_days: int = Field(default=7, ge=1, le=30)
    max_stock_adjustment_percent: int = Field(default=50, ge=10, le=100)
    invite_token_expiry_days: int = Field(default=7, ge=1, le=30)
    
    # ─────────────────────────────────────────────────────────────
    # Notifications (Background Tasks)
    # ─────────────────────────────────────────────────────────────
    # Slack webhook for alerts (optional)
    slack_webhook_url: str | None = Field(default=None)
    
    # Generic webhook for alerts (optional, e.g., PagerDuty, Opsgenie)
    alert_webhook_url: str | None = Field(default=None)
    
    # Email settings for digest/reports (optional)
    smtp_host: str | None = Field(default=None)
    smtp_port: int = Field(default=587)
    smtp_username: str | None = Field(default=None)
    smtp_password: str | None = Field(default=None)
    email_from: str | None = Field(default=None)
    alert_email_recipients: list[str] = Field(default_factory=list)
    
    # Alert settings
    alert_dedup_window_seconds: int = Field(default=3600, ge=300, le=86400)
    alert_rate_limit_per_hour: int = Field(default=50, ge=10, le=500)
    
    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v):
        """Parse comma-separated origins from env var."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @field_validator("alert_email_recipients", mode="before")
    @classmethod
    def parse_email_recipients(cls, v):
        """Parse comma-separated email recipients from env var."""
        if isinstance(v, str):
            return [email.strip() for email in v.split(",") if email.strip()]
        return v
    
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance.
    
    Why cached?
    - Settings don't change at runtime
    - Avoid re-parsing env vars on every request
    - Single source of truth
    """
    return Settings()
