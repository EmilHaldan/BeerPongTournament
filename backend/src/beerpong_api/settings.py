"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend directory (if present)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)


class Settings:
    """Application configuration from environment variables."""

    COSMOS_ENDPOINT: str
    COSMOS_KEY: str
    COSMOS_DATABASE: str
    COSMOS_CONTAINER: str
    ADMIN_TOKEN: str
    CORS_ORIGINS: list[str]

    def __init__(self) -> None:
        self.COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
        self.COSMOS_KEY = os.environ.get("COSMOS_KEY", "")
        self.COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "beerpong")
        self.COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "matches")
        self.ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "changeme")
        cors_raw = os.environ.get("CORS_ORIGINS", "*")
        self.CORS_ORIGINS = [o.strip() for o in cors_raw.split(",")]
        self.TEAMS_CSV_PATH = os.environ.get("TEAMS_CSV_PATH", "teams.csv")
        self.HEAT_TIMER = int(os.environ.get("HEAT_TIMER", "600"))

    @property
    def is_cosmos_configured(self) -> bool:
        """Return True if Cosmos DB connection details are set."""
        return bool(self.COSMOS_ENDPOINT and self.COSMOS_KEY)


def get_settings() -> Settings:
    """Return a Settings instance."""
    return Settings()
