"""All runtime settings, loaded from the environment (and an optional .env file)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    tz: str = "Asia/Kathmandu"
    data_dir: Path = Path("/data")

    google_oauth_client_file: Path | None = None
    gmail_token_file: Path | None = None
    alert_email_to: str | None = None
    gmail_lookback_days: int = 15
    linkedin_alert_senders: str = "jobalerts-noreply@linkedin.com,jobs-listings@linkedin.com"
    linkedin_notification_sender: str = "notifications-noreply@linkedin.com"

    ntfy_topic: str | None = None
    ntfy_url: str = "https://ntfy.sh"

    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_resident_models: str = "qwen2.5:3b"
    anthropic_api_key: str | None = None
    claude_model: str = "claude-haiku-4-5-20251001"
    xai_api_key: str | None = None
    grok_model: str = "grok-build-0.1"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    ai_ollama_timeout_seconds: int = 30
    ai_hosted_timeout_seconds: int = 20
    ai_hosted_daily_cap: int = 200

    searxng_url: str = "http://searxng:8080"
    brave_api_key: str | None = None
    brave_monthly_cap: int = 950
    search_queries_per_hour: int = 2

    github_username: str | None = None
    github_token: str | None = None
    nepal_list_url: str = (
        "https://raw.githubusercontent.com/mesaugat/tech-companies-in-nepal/master/README.md"
    )

    max_job_age_days: int = 14
    retention_days: int = 30

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobbot.sqlite3"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def profile_dir(self) -> Path:
        return self.data_dir / "profile"

    @property
    def resolved_gmail_token_file(self) -> Path:
        return self.gmail_token_file or (self.secrets_dir / "gmail_token.json")

    @property
    def resolved_oauth_client_file(self) -> Path | None:
        return self.google_oauth_client_file
