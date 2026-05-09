"""MCP server for the Tools CRM.

Exposes the same CRUD operations as the REST API, shaped as conversational
tools. Designed for Claude Desktop and Cowork: the salesman talks, Claude
calls these tools, the SQLite database underneath stays consistent with
what the web UI shows.

Run as a stdio MCP server. Registered in claude_desktop_config.json by
the install script. When launched by Claude Desktop, stdout is the MCP
protocol channel — never write logs there. All diagnostics go to
~/.tools-crm/mcp.log.

Pass --check to import-and-exit (used by scripts/doctor.py to confirm
the server can boot without speaking the protocol).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path


# ---------- logging ----------
# Set this up FIRST, before any imports that might fail. When Claude Desktop
# spawns this process it captures stderr but silently. Without a file log,
# any boot-time error is invisible.

_LOG_DIR = Path.home() / ".tools-crm"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "mcp.log"

logging.basicConfig(
    filename=str(_LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("flipbook-mcp")
log.info("MCP starting (pid=%s, py=%s)", os.getpid(), sys.executable)


# Ensure the parent app package is importable when launched by Claude Desktop
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from mcp.server import Server  # noqa: E402
    from mcp.server.stdio import stdio_server  # noqa: E402
    from mcp.types import TextContent, Tool  # noqa: E402

    from app import crud  # noqa: E402
    from app.db import init_db, now_iso  # noqa: E402
except Exception:
    log.exception("Failed to import MCP server dependencies")
    raise


server = Server("tools-crm")


# ---------- Tool definitions ----------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_contacts",
            description=(
                "Search contacts by free text (matches name, company, email, notes) "
                "and/or filter by a single tag. Returns a list of matching contacts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free text search"},
                    "tag":   {"type": "string", "description": "Filter by tag (e.g. 'oslo')"},
                    "limit": {"type": "integer", "default": 25},
                },
            },
        ),
        Tool(
            name="get_contact",
            description=(
                "Get full details for a contact, including interaction history. "
                "Pass either a numeric id, or a name like 'Hansen' or 'Hansen @ Byggvarehuset'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id":   {"type": "integer", "description": "Numeric contact id"},
                    "name": {"type": "string",  "description": "Name or 'Name @ Company' shorthand"},
                },
            },
        ),
        Tool(
            name="add_contact",
            description="Create a new contact.",
            inputSchema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name":    {"type": "string"},
                    "company": {"type": "string"},
                    "role":    {"type": "string"},
                    "phone":   {"type": "string"},
                    "email":   {"type": "string"},
                    "tags":    {"type": "string", "description": "Comma-separated tags"},
                    "notes":   {"type": "string"},
                },
            },
        ),
        Tool(
            name="update_contact",
            description="Update fields on an existing contact. Pass the contact id and any fields to change.",
            inputSchema={
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id":      {"type": "integer"},
                    "name":    {"type": "string"},
                    "company": {"type": "string"},
                    "role":    {"type": "string"},
                    "phone":   {"type": "string"},
                    "email":   {"type": "string"},
                    "tags":    {"type": "string"},
                    "notes":   {"type": "string"},
                },
            },
        ),
        Tool(
            name="log_interaction",
            description=(
                "Log a call, email, visit, meeting or other interaction with a contact. "
                "Identify the contact by id, or by name (resolved with the same shorthand as get_contact). "
                "Optionally set a follow-up date (YYYY-MM-DD)."
            ),
            inputSchema={
                "type": "object",
                "required": ["channel", "summary"],
                "properties": {
                    "contact_id":     {"type": "integer"},
                    "contact_name":   {"type": "string"},
                    "channel":        {"type": "string", "enum": ["call", "email", "visit", "meeting", "other"]},
                    "summary":        {"type": "string"},
                    "follow_up_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "occurred_at":    {"type": "string", "description": "ISO timestamp; defaults to now"},
                },
            },
        ),
        Tool(
            name="complete_followup",
            description=(
                "Mark a follow-up as done. Pass either interaction_id (precise) "
                "or contact_name (closes all open follow-ups for that contact). "
                "Note: logging a new interaction with a contact already auto-closes "
                "their open follow-ups, so call this only when the follow-up was "
                "cancelled or handled outside of a logged interaction."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "interaction_id": {"type": "integer"},
                    "contact_name":   {"type": "string", "description": "Name or 'Name @ Company' shorthand"},
                },
            },
        ),
        Tool(
            name="todays_followups",
            description="Return open follow-ups due today or earlier (overdue). Excludes already-completed ones.",
            inputSchema={
                "type": "object",
                "properties": {
                    "today": {"type": "string", "description": "YYYY-MM-DD; defaults to today"},
                },
            },
        ),
        Tool(
            name="recent_activity",
            description="Return interactions logged in the last N days (default 7).",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                },
            },
        ),
        Tool(
            name="list_tags",
            description="List all tags in use across contacts.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ---------- Tool implementations ----------

def _ok(payload) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


def _err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": message}))]


def _resolve_contact(args: dict) -> dict | None:
    if "id" in args and args["id"] is not None:
        return crud.get_contact(int(args["id"]))
    if "contact_id" in args and args["contact_id"] is not None:
        return crud.get_contact(int(args["contact_id"]))
    name = args.get("name") or args.get("contact_name")
    if name:
        return crud.find_contact_by_name(name)
    return None


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log.info("tool call: %s args=%s", name, sorted(arguments.keys()))
    try:
        if name == "search_contacts":
            results = crud.list_contacts(
                query=arguments.get("query"),
                tag=arguments.get("tag"),
                limit=int(arguments.get("limit", 25)),
            )
            return _ok({"count": len(results), "contacts": results})

        if name == "get_contact":
            contact = _resolve_contact(arguments)
            if contact is None:
                return _err("Contact not found")
            contact["interactions"] = crud.list_interactions(contact_id=contact["id"])
            return _ok(contact)

        if name == "add_contact":
            created = crud.create_contact(
                name=arguments["name"],
                company=arguments.get("company"),
                role=arguments.get("role"),
                phone=arguments.get("phone"),
                email=arguments.get("email"),
                tags=arguments.get("tags", ""),
                notes=arguments.get("notes", ""),
            )
            return _ok(created)

        if name == "update_contact":
            updated = crud.update_contact(
                int(arguments["id"]),
                **{k: v for k, v in arguments.items() if k != "id"},
            )
            if updated is None:
                return _err("Contact not found")
            return _ok(updated)

        if name == "log_interaction":
            contact = _resolve_contact(arguments)
            if contact is None:
                return _err("Could not resolve contact. Provide contact_id or contact_name.")
            interaction = crud.create_interaction(
                contact_id=contact["id"],
                channel=arguments["channel"],
                summary=arguments["summary"],
                occurred_at=arguments.get("occurred_at"),
                follow_up_date=arguments.get("follow_up_date"),
            )
            return _ok({"contact": {"id": contact["id"], "name": contact["name"]}, "interaction": interaction})

        if name == "complete_followup":
            iid = arguments.get("interaction_id")
            if iid is not None:
                updated = crud.complete_followup(int(iid))
                if updated is None:
                    return _err("Interaction not found")
                return _ok(updated)
            contact = _resolve_contact(arguments)
            if contact is None:
                return _err("Provide interaction_id or contact_name.")
            n = crud.complete_followups_for_contact(contact["id"])
            return _ok({"contact": {"id": contact["id"], "name": contact["name"]}, "closed": n})

        if name == "todays_followups":
            today = arguments.get("today") or now_iso()[:10]
            return _ok({"today": today, "followups": crud.todays_followups(today)})

        if name == "recent_activity":
            days = int(arguments.get("days", 7))
            return _ok({"days": days, "interactions": crud.recent_activity(days)})

        if name == "list_tags":
            return _ok({"tags": crud.all_tags()})

        return _err(f"Unknown tool: {name}")
    except Exception as e:
        log.exception("tool %s raised", name)
        return _err(f"{type(e).__name__}: {e}")


async def main() -> None:
    init_db()
    log.info("Server initialized; starting stdio loop")
    try:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())
    except Exception:
        log.exception("Stdio loop crashed")
        raise
    finally:
        log.info("Stdio loop ended")


if __name__ == "__main__":
    if "--check" in sys.argv:
        # Used by scripts/doctor.py to verify the server can boot. We import
        # everything (already happened at module load) and probe the database
        # without entering the protocol loop.
        try:
            init_db()
            print("OK")
            sys.exit(0)
        except Exception as e:
            log.exception("--check failed")
            print(f"FAIL: {e}", file=sys.stderr)
            sys.exit(1)
    try:
        asyncio.run(main())
    except Exception:
        log.exception("MCP server crashed at startup")
        raise
