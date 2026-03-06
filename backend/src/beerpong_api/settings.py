"""Application settings loaded from environment variables."""

from __future__ import annotations

import os


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

    @property
    def is_cosmos_configured(self) -> bool:
        """Return True if Cosmos DB connection details are set."""
        return bool(self.COSMOS_ENDPOINT and self.COSMOS_KEY)


def get_settings() -> Settings:
    """Return a Settings instance."""
    return Settings()
