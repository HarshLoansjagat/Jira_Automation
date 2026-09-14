from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str = (
        "sqlite:////tmp/dc_ai_reports.db"
        if os.getenv("VERCEL")
        else "sqlite:///./dc_ai_reports.db"
    )
    REPORT_TEMPLATE_PATH: str = ""
    GMAIL_USER: Optional[str] = None
    GMAIL_APP_PASSWORD: Optional[str] = None
    JIRA_CSV_PATH: Optional[str] = None
    JIRA_BASE_URL: Optional[str] = None
    JIRA_EMAIL: Optional[str] = None
    JIRA_API_TOKEN: Optional[str] = None
    JIRA_PROJECT_KEY: Optional[str] = None
    JIRA_BOARD_ID: Optional[str] = None

    # Microsoft Graph
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_TENANT_ID: Optional[str] = None
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/api/outlook/callback"

    # AI Providers
    GEMINI_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    DEFAULT_AI_PROVIDER: str = "none"

    # Storage
    REPORT_STORAGE_PATH: str = (
        "/tmp/generated_reports"
        if os.getenv("VERCEL")
        else "./generated_reports"
    )
    UPLOAD_STORAGE_PATH: str = "/tmp/uploads" if os.getenv("VERCEL") else "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 20

    # Security
    SECRET_KEY: str = "change-this-to-a-random-secret-key"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()

# Ensure storage directories exist
os.makedirs(settings.REPORT_STORAGE_PATH, exist_ok=True)
os.makedirs(settings.UPLOAD_STORAGE_PATH, exist_ok=True)
