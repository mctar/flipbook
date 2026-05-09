# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Flipbook (package name `tools-crm`) is a single-user, single-machine CRM for a tools salesman. One SQLite file is the entire datastore. Three surfaces (web UI, REST API, MCP server) all call the same Python functions in `app/crud.py` — keep that the single source of truth, never duplicate query logic into the API or MCP layer.

## Common commands

All commands run via `uv` (installed by `scripts/install.sh` if missing). Dependencies live in a project-local `.venv`.

```bash
./scripts/install.sh         # idempotent: install uv + Tailscale, sync deps, init db, register MCP, run doctor
./scripts/start.sh           # uvicorn app.main:app on 0.0.0.0:8765
./scripts/doctor.sh          # cross-platform self-test — uv, .venv, db, MCP, Tailscale, port
./scripts/repair.sh          # re-runs install (does NOT touch the db)

uv sync                      # install/update dependencies
uv run python -c "from app.db import init_db; init_db()"   # create db only
uv run uvicorn app.main:app --host 0.0.0.0 --port 8765 --reload   # dev server with reload
uv run python mcp/server.py --check   # boot the MCP server and exit (used by doctor)
uv run python mcp/server.py           # run the MCP server standalone (stdio)
```

The Windows install (`scripts\install.bat`) self-elevates via UAC because it adds a Windows Defender Firewall rule for port 8765 and creates a Startup-folder shortcut. On Windows the server is launched silently at login by `scripts\start_silent.vbs`, which logs to `~/.tools-crm/server.log`.

There is no test suite, linter, or formatter configured. If you add tests, use `TOOLS_CRM_DB` env var to point at a temp SQLite file so they don't touch `~/.tools-crm/crm.db`.

## Architecture

### Three surfaces, one core

```
web/index.html ──┐
                 ├── HTTP ──> app/main.py (FastAPI)  ──┐
mobile via       │                                      ├──> app/crud.py ──> app/db.py ──> SQLite
Tailscale ───────┘                                      │
                                                        │
Claude Desktop / Cowork ──── stdio ──> mcp/server.py ───┘
```

- `app/crud.py` — every read/write goes through here. The FastAPI handlers in `app/main.py` and the MCP tool handlers in `mcp/server.py` are thin adapters that call `crud` functions and shape the response. When adding behavior, add it to `crud.py` first, then expose it on each surface.
- `app/db.py` — raw `sqlite3`, no ORM. Schema is the `SCHEMA` string; `init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS`). `get_conn()` is a context manager that auto-commits on exit and enforces foreign keys.
- `app/main.py` — FastAPI service. Lifespan handler calls `init_db()`. Mounts `web/` as static (so `/static/alpine.min.js`, `/static/icon.svg`, `/static/manifest.json` all serve from `web/`). Serves `index.html` at `/` with `Cache-Control: no-cache` so iterative edits show on a normal reload. Permissive CORS by design.
- `mcp/server.py` — stdio MCP server registered as `tools-crm` in `claude_desktop_config.json`. Adds the project root to `sys.path` so `from app import crud` works when launched from anywhere. **Logging**: file logger writes to `~/.tools-crm/mcp.log` from process start — when Claude Desktop spawns this and something fails, the trace lives there. **stdout is the MCP protocol channel** — never `print()` to it. Pass `--check` to import-and-exit (used by `scripts/doctor.py` to verify the server can boot).
- `web/index.html` — single file, Alpine.js. **Alpine is vendored locally** at `web/alpine.min.js` (served as `/static/alpine.min.js`) — do NOT switch to a CDN version, an email-obfuscator silently turned the `alpinejs@3.x` URL into `[email protected]` once and bricked the entire UI without any console errors. PWA assets (`web/manifest.json`, `web/icon.svg`) make Add-to-Home-Screen produce a real-looking app tile on iOS/Android.

### Data model (v1, intentionally minimal)

Three tables: `contacts`, `interactions`, `import_log`. Tags are a comma-separated string in `contacts.tags` — `_normalize_tags()` lowercases, strips, and dedupes. Tag filtering uses the `(',' || tags || ',') LIKE '%,tag,%'` trick so substring tags don't false-match. No `deals`, no `products`, no pipeline. See `docs/v2_questions.md` before proposing schema additions — v2 scope is deliberately gated on real usage feedback.

### Bench / Coming up / Recent (the three lists on `/api/today`)

- **Bench / `followups`** — open follow-ups due today or overdue.
- **Coming up / `upcoming`** — open follow-ups in the next N days (default 7), strictly after today.
- **Recent / `recent`** — closed-loop interactions in the last N days. Excludes rows with an open follow-up (those would double-paint the Bench).

A row is "open" when `follow_up_date IS NOT NULL AND completed_at IS NULL`. `complete_followup()` sets `completed_at`. `create_interaction()` auto-closes any older open follow-ups for the same contact — logging the call IS the completion.

### Database location

Production path: `~/.tools-crm/crm.db` (Mac) / `%USERPROFILE%\.tools-crm\crm.db` (Windows). Override with `TOOLS_CRM_DB` env var. The directory is auto-created by `init_db()`.

### Excel import (idempotent)

`crud.import_contacts_from_rows()` hashes each row (`source|name|company|email`, sha256) and skips hashes already in `import_log`. Re-importing the same file is safe — only new/changed rows get inserted. Header recognition is bilingual (Norwegian + English) via `HEADER_MAP`; add new aliases there.

### Excel export (round-trip safe)

`GET /api/export/excel` streams a two-sheet workbook (`Contacts` + `Interactions`). Contact column headers match the English aliases the importer recognises, so a user can export, edit in Excel, and re-import the same file — `import_log` row-hash dedupe ensures unchanged rows are skipped.

### Contact resolution by name

MCP tools accept either a numeric `id` or a `"Name @ Company"` shorthand resolved by `crud.find_contact_by_name()`. `_resolve_contact()` in `mcp/server.py` is the dispatcher. Returns the most recently updated match — so if you change resolution semantics, do it there, not in each tool handler.

## Things to know before changing code

- **Migrations live in `app/db.py::_migrate()`.** `init_db` runs it after `executescript(SCHEMA)`. The pattern: read `PRAGMA table_info`, `ALTER TABLE ADD COLUMN` if missing. Idempotent. Don't reach for an ORM or Alembic — the schema is too small to warrant it.
- **`updated_at` is touched on interaction insert.** `create_interaction` updates the parent contact's `updated_at` so it sorts to the top of the Bench. Preserve this if you refactor.
- **MCP and FastAPI must stay in sync.** When adding a CRUD operation, expose it on both surfaces or explicitly note why one surface is omitting it. The README's "single source of truth" promise is load-bearing.
- **The web UI is responsive and one-handed.** It's used in a garage. Don't introduce hover-only interactions or tiny touch targets.
- **Phone access goes through Tailscale**, hence `host=0.0.0.0`. Don't bind to localhost.
