# Beer Pong Tournament API

FastAPI backend for tracking beer pong matches and computing leaderboards.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `COSMOS_ENDPOINT` | Azure Cosmos DB endpoint URL | _(required in prod)_ |
| `COSMOS_KEY` | Azure Cosmos DB primary key | _(required in prod)_ |
| `COSMOS_DATABASE` | Cosmos database name | `beerpong` |
| `COSMOS_CONTAINER` | Cosmos container name | `matches` |
| `ADMIN_TOKEN` | Token for admin endpoints | `changeme` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `*` |

## Architecture

```
src/beerpong_api/
  main.py          # FastAPI app + lifespan
  settings.py      # Env var configuration
  api/
    routes.py      # HTTP endpoints (delegates to DAL)
  dal/
    matches.py     # insert_match, list_matches, reset_matches
    leaderboard.py # compute_leaderboard
  db/
    client.py      # Cosmos DB client init + ContainerLike protocol
    models.py      # Pydantic models
```

**DAL boundary**: API routes never access the DB client directly — they call DAL
functions which return typed Pydantic models.

## Development

```bash
just install     # uv sync
just run         # start dev server on :8000
just test        # pytest
just typecheck   # basedpyright
just lint        # ruff
just check       # all of the above
```
