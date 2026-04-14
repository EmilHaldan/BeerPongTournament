"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from beerpong_api.api.routes import router
from beerpong_api.db.client import init_db, init_local_db
from beerpong_api.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise DB on startup – Cosmos in prod, SQLite locally."""
    settings = get_settings()
    if settings.is_cosmos_configured:
        init_db(settings)
    else:
        init_local_db()
        print("  ⚡ Using local SQLite database (beerpong_local.db)")
    yield


app = FastAPI(
    title="Beer Pong Tournament API",
    version="0.1.0",
    description="Simple API for tracking beer pong matches and leaderboard.",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def main() -> None:
    """Run the API server via Uvicorn."""
    uvicorn.run("beerpong_api.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
