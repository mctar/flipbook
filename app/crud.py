"""Core CRUD operations.

These functions are the single source of truth for all data operations.
Both the FastAPI endpoints and the MCP tools call into here, so behavior
is identical across surfaces.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .db import get_conn, now_iso, row_to_dict


# ---------- Contacts ----------

def list_contacts(
    query: str | None = None,
    tag: str | None = None,
    limit: int = 200,
) -> list[dict]:
    sql = "SELECT * FROM contacts WHERE 1=1"
    params: list[Any] = []
    if query:
        sql += " AND (name LIKE ? OR company LIKE ? OR email LIKE ? OR notes LIKE ?)"
        like = f"%{query}%"
        params.extend([like, like, like, like])
    if tag:
        sql += " AND (',' || tags || ',') LIKE ?"
        params.append(f"%,{tag},%")
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_contact(contact_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return row_to_dict(row)


def find_contact_by_name(needle: str) -> dict | None:
    """Resolve a contact by partial name or 'Name @ Company' shorthand.

    Returns the most recently updated match. Used by MCP tools so the
    salesman can say "Hansen at Byggvarehuset" instead of looking up an ID.
    """
    name_part, _, company_part = needle.partition("@")
    name_part = name_part.strip()
    company_part = company_part.strip()

    sql = "SELECT * FROM contacts WHERE name LIKE ?"
    params: list[Any] = [f"%{name_part}%"]
    if company_part:
        sql += " AND company LIKE ?"
        params.append(f"%{company_part}%")
    sql += " ORDER BY updated_at DESC LIMIT 1"

    with get_conn() as conn:
        row = conn.execute(sql, params).fetchone()
    return row_to_dict(row)


def create_contact(
    name: str,
    company: str | None = None,
    role: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    tags: str = "",
    notes: str = "",
) -> dict:
    ts = now_iso()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO contacts (name, company, role, phone, email, tags, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, company, role, phone, email, _normalize_tags(tags), notes, ts, ts),
        )
        contact_id = cur.lastrowid
    return get_contact(contact_id)  # type: ignore[return-value]


def update_contact(contact_id: int, **fields: Any) -> dict | None:
    allowed = {"name", "company", "role", "phone", "email", "tags", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_contact(contact_id)
    if "tags" in updates:
        updates["tags"] = _normalize_tags(updates["tags"])
    updates["updated_at"] = now_iso()
    sql = "UPDATE contacts SET " + ", ".join(f"{k} = ?" for k in updates) + " WHERE id = ?"
    with get_conn() as conn:
        conn.execute(sql, [*updates.values(), contact_id])
    return get_contact(contact_id)


def delete_contact(contact_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    return cur.rowcount > 0


def _normalize_tags(tags: str) -> str:
    """Lowercase, deduplicate, strip whitespace. Stored as comma-joined string."""
    parts = [t.strip().lower() for t in (tags or "").split(",") if t.strip()]
    seen: dict[str, None] = {}
    for p in parts:
        seen[p] = None
    return ",".join(seen.keys())


def all_tags() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT tags FROM contacts WHERE tags <> ''").fetchall()
    bag: set[str] = set()
    for r in rows:
        for t in (r["tags"] or "").split(","):
            t = t.strip()
            if t:
                bag.add(t)
    return sorted(bag)


# ---------- Interactions ----------

def list_interactions(contact_id: int | None = None, limit: int = 100) -> list[dict]:
    if contact_id is not None:
        sql = "SELECT * FROM interactions WHERE contact_id = ? ORDER BY occurred_at DESC LIMIT ?"
        params: list[Any] = [contact_id, limit]
    else:
        sql = "SELECT * FROM interactions ORDER BY occurred_at DESC LIMIT ?"
        params = [limit]
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def create_interaction(
    contact_id: int,
    channel: str,
    summary: str,
    occurred_at: str | None = None,
    follow_up_date: str | None = None,
) -> dict:
    # Normalize: the web UI sends "" when the date input is blank.
    follow_up_date = follow_up_date or None
    occurred = occurred_at or now_iso()
    created = now_iso()
    with get_conn() as conn:
        # Auto-close any older open follow-ups for this contact: logging a new
        # interaction *is* the completion. Flip shouldn't have to mark "done"
        # and then "log call" — those are one event, not two.
        conn.execute(
            """UPDATE interactions
                  SET completed_at = ?
                WHERE contact_id = ?
                  AND follow_up_date IS NOT NULL
                  AND completed_at IS NULL""",
            (created, contact_id),
        )
        cur = conn.execute(
            """INSERT INTO interactions (contact_id, occurred_at, channel, summary, follow_up_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (contact_id, occurred, channel, summary, follow_up_date, created),
        )
        # Touch the contact so it sorts to the top of recent activity
        conn.execute("UPDATE contacts SET updated_at = ? WHERE id = ?", (created, contact_id))
        interaction_id = cur.lastrowid
        row = conn.execute("SELECT * FROM interactions WHERE id = ?", (interaction_id,)).fetchone()
    return dict(row)


def complete_followup(interaction_id: int) -> dict | None:
    """Mark a single interaction's follow-up as done. Returns the updated row."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE interactions SET completed_at = ? WHERE id = ? AND completed_at IS NULL",
            (now_iso(), interaction_id),
        )
        row = conn.execute("SELECT * FROM interactions WHERE id = ?", (interaction_id,)).fetchone()
    return row_to_dict(row)


def complete_followups_for_contact(contact_id: int) -> int:
    """Close every open follow-up for a contact. Returns rows affected."""
    with get_conn() as conn:
        cur = conn.execute(
            """UPDATE interactions
                  SET completed_at = ?
                WHERE contact_id = ?
                  AND follow_up_date IS NOT NULL
                  AND completed_at IS NULL""",
            (now_iso(), contact_id),
        )
        return cur.rowcount


def todays_followups(today: str) -> list[dict]:
    """Return open follow-ups due today or overdue, with contact info.

    Closed follow-ups (completed_at set) are excluded — they live in the
    contact's interaction history rather than the Bench.
    """
    sql = """
        SELECT i.*, c.name AS contact_name, c.company AS contact_company, c.phone AS contact_phone
        FROM interactions i
        JOIN contacts c ON c.id = i.contact_id
        WHERE i.follow_up_date IS NOT NULL
          AND i.completed_at IS NULL
          AND i.follow_up_date <= ?
        ORDER BY i.follow_up_date ASC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (today,)).fetchall()
    return [dict(r) for r in rows]


def upcoming_followups(today: str, days: int = 7) -> list[dict]:
    """Open follow-ups in the next `days` days (strictly after `today`).

    Today's and overdue follow-ups go through `todays_followups` instead — this
    one is for the "what's coming up?" section so users can see the week ahead.
    """
    sql = """
        SELECT i.*, c.name AS contact_name, c.company AS contact_company, c.phone AS contact_phone
        FROM interactions i
        JOIN contacts c ON c.id = i.contact_id
        WHERE i.follow_up_date IS NOT NULL
          AND i.completed_at IS NULL
          AND i.follow_up_date > ?
          AND i.follow_up_date <= date(?, '+' || ? || ' days')
        ORDER BY i.follow_up_date ASC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (today, today, int(days))).fetchall()
    return [dict(r) for r in rows]


def recent_activity(days: int = 7) -> list[dict]:
    """Return closed-loop interactions from the last N days.

    Open follow-ups already surface in `todays_followups` and
    `upcoming_followups`. Including them here too would double-paint the
    Bench, so we exclude rows that still have an unresolved follow-up.
    What's left: interactions with no follow-up date (one-off contact)
    plus follow-ups that have been completed.
    """
    sql = """
        SELECT i.*, c.name AS contact_name, c.company AS contact_company
        FROM interactions i
        JOIN contacts c ON c.id = i.contact_id
        WHERE i.occurred_at >= datetime('now', ?)
          AND NOT (i.follow_up_date IS NOT NULL AND i.completed_at IS NULL)
        ORDER BY i.occurred_at DESC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (f"-{int(days)} days",)).fetchall()
    return [dict(r) for r in rows]


# ---------- Excel import ----------

# Header aliases. Lowercase, stripped. Norwegian and English.
HEADER_MAP = {
    "name":    {"name", "navn", "fullt navn", "kontaktperson", "contact", "contact name"},
    "company": {"company", "firma", "bedrift", "selskap", "kunde", "customer"},
    "role":    {"role", "title", "rolle", "stilling", "tittel"},
    "phone":   {"phone", "telefon", "tlf", "mobile", "mobil"},
    "email":   {"email", "e-mail", "e-post", "epost", "mail"},
    "notes":   {"notes", "notater", "notat", "kommentar", "comment"},
    "tags":    {"tags", "tag", "etiketter", "merkelapp"},
}


def map_excel_columns(headers: list[str]) -> dict[str, str | None]:
    """Map normalized headers from the Excel file to our contact fields."""
    out: dict[str, str | None] = {f: None for f in HEADER_MAP}
    normalized = {h: h.strip().lower() for h in headers}
    for field, aliases in HEADER_MAP.items():
        for original, lowered in normalized.items():
            if lowered in aliases:
                out[field] = original
                break
    return out


def _row_hash(name: str, company: str | None, email: str | None, source: str) -> str:
    key = f"{source}|{(name or '').strip().lower()}|{(company or '').strip().lower()}|{(email or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def import_contacts_from_rows(
    rows: list[dict[str, Any]],
    column_map: dict[str, str | None],
    source: str = "excel",
) -> dict:
    """Insert contacts from parsed Excel rows. Idempotent via row_hash."""
    created = 0
    skipped = 0
    errors: list[str] = []

    with get_conn() as conn:
        for idx, row in enumerate(rows, start=2):  # row 2 because row 1 is the header
            def field(f: str) -> str:
                col = column_map.get(f)
                if col is None:
                    return ""
                v = row.get(col)
                if v is None:
                    return ""
                return str(v).strip()

            name = field("name")
            if not name:
                errors.append(f"Row {idx}: missing name, skipped")
                continue

            company = field("company") or None
            email = field("email") or None
            h = _row_hash(name, company, email, source)

            existing = conn.execute("SELECT contact_id FROM import_log WHERE row_hash = ?", (h,)).fetchone()
            if existing:
                skipped += 1
                continue

            ts = now_iso()
            cur = conn.execute(
                """INSERT INTO contacts (name, company, role, phone, email, tags, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    name,
                    company,
                    field("role") or None,
                    field("phone") or None,
                    email,
                    _normalize_tags(field("tags")),
                    field("notes"),
                    ts, ts,
                ),
            )
            conn.execute(
                "INSERT INTO import_log (row_hash, contact_id, source, imported_at) VALUES (?, ?, ?, ?)",
                (h, cur.lastrowid, source, ts),
            )
            created += 1

    return {"created": created, "skipped": skipped, "errors": errors}


# ---------- Excel export ----------

# Round-trip-friendly: contact column headers match the English aliases the
# importer recognises, so a user can export, edit in Excel, and re-import the
# same file. The "ID" column is informational; the importer ignores it.
EXPORT_CONTACT_HEADERS = ["ID", "Name", "Company", "Role", "Phone", "Email", "Tags", "Notes", "Created", "Updated"]
EXPORT_INTERACTION_HEADERS = ["ID", "Contact ID", "Contact Name", "When", "Channel", "Summary", "Follow Up", "Completed"]


def export_rows() -> tuple[list[list[Any]], list[list[Any]]]:
    """Return (contacts_rows, interactions_rows) for the workbook export.

    First row of each list is the header. Subsequent rows are data.
    """
    with get_conn() as conn:
        contacts = conn.execute("SELECT * FROM contacts ORDER BY id").fetchall()
        interactions = conn.execute(
            """SELECT i.*, c.name AS contact_name
                 FROM interactions i
                 JOIN contacts c ON c.id = i.contact_id
                 ORDER BY i.id"""
        ).fetchall()

    c_rows: list[list[Any]] = [EXPORT_CONTACT_HEADERS]
    for c in contacts:
        c_rows.append([
            c["id"], c["name"], c["company"], c["role"], c["phone"],
            c["email"], c["tags"], c["notes"], c["created_at"], c["updated_at"],
        ])

    i_rows: list[list[Any]] = [EXPORT_INTERACTION_HEADERS]
    for i in interactions:
        i_rows.append([
            i["id"], i["contact_id"], i["contact_name"], i["occurred_at"],
            i["channel"], i["summary"], i["follow_up_date"], i["completed_at"],
        ])

    return c_rows, i_rows
