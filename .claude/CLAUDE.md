# BeerPongTournament — Project Rules for Claude

Personal repo owned by EmilHaldan. Python 3.12 FastAPI backend, vanilla JS frontend,
Terraform infra on Azure. Main auto-deploys — treat main as production.

## Architecture

Strict layering. Do not bypass:

```
api/routes.py  →  dal/*.py  →  db/client.py  →  Cosmos / SQLite
```

- Routes are thin: parse input, call DAL, return response. **Never** import
  `azure.cosmos`, touch `db/client.py`, or hit a container directly from a route.
- All reads, writes, queries, and transactions go through `dal/`.
- `db/client.py` exposes the container singletons (`get_container`,
  `get_teams_container`, `get_state_container`) plus setters used by tests.
- Raw SQL / Cosmos queries live **inside** the DAL only and must use bound
  parameters — no f-string query building.

## Backend conventions

- Python 3.12 everywhere: `requires-python = ">=3.12"`, `basedpyright.pythonVersion
  = "3.12"`, `ruff.target-version = "py312"`, Docker base image on `python:3.12`.
  Keep these aligned.
- Package manager: `uv`. Run commands as `uv run <tool>`.
- Typing: `str | None` unions, `from __future__ import annotations` at file top,
  absolute imports only.
- Formatting: `ruff format`, line length 100.
- basedpyright runs in **standard** mode, not strict. The `reportUnknown*` rules
  are deliberately relaxed because the Cosmos SDK returns `Any`/opaque types.
  Do not tighten these without discussion.
- Existing `# pyright: ignore[...]` comments exist for the same reason — leave
  them unless you have replaced the Cosmos call with a typed wrapper.

## Domain rules (don't break these)

- **Team + match names** are normalised via `.strip().title()` before persist.
  Apply the same normalisation on any new name-carrying field.
- **Heat is server-authoritative.** `POST /matches` overwrites the client's
  `heat` value with the current heat from state. Do not trust client-supplied
  heat on create.
- **Heat rotation in `dal/heat.py` is subtle** — it uses the circle method with
  cycle detection to generate pairings. Any change here needs a regression test
  covering: odd team count, team count change mid-tournament, cycle detection
  path, and advancing through a full cycle.
- **`teams.csv` auto-loads at startup** if the teams container is empty. Keep
  that bootstrap path working when touching startup code.

## Admin auth

Admin endpoints use a header token, not OAuth:

```python
def require_admin(token: str = Header(..., alias="X-Admin-Token")) -> None:
    if token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Forbidden")
```

- Alias is always `X-Admin-Token`.
- Compare against `settings.ADMIN_TOKEN`.
- Mismatch → `HTTPException(403)`. Do not return 401 or 400.

## Tests

- `backend/tests/conftest.py` defines an **autouse** `FakeContainer` fixture
  that injects in-memory containers for `matches`, `teams`, and `state` before
  every test.
- Tests must never hit real Cosmos or the local SQLite file. If a new test
  needs DB access, extend `FakeContainer` — do not bypass the fixture.
- Use `Mock(spec=Cls)`, not bare `MagicMock`, unless dunders are needed.
- Arrange-Act-Assert. Test names: `test_<what>_<condition>_<expected>()`.
- Run `uv run pytest -v` before claiming tests pass.

## Infra (Terraform)

- `infra/main.tf` is the single source of truth for Azure resources.
- **`azurerm_static_web_app.frontend` is pinned to `westeurope`** even when
  `var.location` is elsewhere (northeurope, etc.). Azure SWA does not support
  northeurope — this is deliberate, not a bug. Do not "fix" it.
- Run `terraform fmt -recursive` after any `.tf` edit. CI checks format.
- Cosmos containers (`matches`, `teams`, `state`) all use partition key
  `/tournamentId`. Mirror that on any new container.

## Verification before claiming done

If you have not run the command in the current response, do not claim it
passes. Minimum before reporting:

```
cd backend && uv sync
cd backend && uv run ruff check src/ tests/
cd backend && uv run basedpyright src/
cd backend && uv run pytest -v
cd infra    && terraform fmt -check -recursive
```

All five must exit 0. Fix and re-run if any fail.

## Git + deploy

- **Auto-commit OK** on this repo. Match the style of recent `git log` — short
  imperative or descriptive titles, single-line where the existing history is
  single-line. Do not invent a style the repo doesn't already use.
- **Commit messages: use `git commit -m "..."` with double-quoted strings.**
  Never use heredoc / `<<EOF` / multi-line bash redirection for commit
  messages. This has been corrected repeatedly.
- **Never `git push` without explicit user approval.** Confirm the branch
  before pushing. Never force-push. Never push to any branch other than the
  current one unless told to.
- **Push to `main` auto-deploys to Azure.** Treat `main` as production. No
  experimental commits directly on main.

## Scope discipline

- Do not reformat files you did not functionally change.
- Do not rename symbols that aren't load-bearing to the task.
- If you spot unrelated style drift, note it and suggest a dedicated cleanup
  task rather than fixing inline — unless the scope is under ~5 files.
