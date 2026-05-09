# Flipbook

A small, local book of contacts for Flip. Runs on his laptop. Three ways to use it:

1. **Web browser** at `http://localhost:8765`. Works on the phone too via Tailscale
2. **Claude Desktop chat**: talk to it: *"log a call with Hansen at Byggvarehuset"* — works in the regular chat tab, not in Cowork (see below)
3. **API** if he ever wants to script something

The data lives in one SQLite file. Back that file up and the whole thing is backed up.

- Mac:     `~/.tools-crm/crm.db`
- Windows: `%USERPROFILE%\.tools-crm\crm.db`

---

## Setup

### Mac

```bash
git clone <repo-url> flipbook
cd flipbook
./scripts/install.sh
./scripts/start.sh
```

### Windows

1. Clone (or download) the repo.
2. Double-click `scripts\install.bat`.
3. Double-click `scripts\start.bat`. The browser opens automatically.

The installer:

- Installs `uv` (a fast Python package manager) if not already there
- Installs dependencies into a local `.venv` inside the project
- Creates the database
- Registers Flipbook as an MCP server with Claude Desktop
- (Windows) Installs Tailscale via `winget`, opens an inbound firewall rule for port 8765, and creates a Startup-folder shortcut so Flipbook runs at every login
- (Windows) Adjusts the **plugged-in** power profile: never idle-sleep, never hibernate, lid-close = do nothing. The battery profile is unchanged. This is so the phone can reach Flipbook over Tailscale even when the laptop lid is closed (as long as the charger is plugged in). To revert: `powercfg /change standby-timeout-ac 30` (or any number of minutes you prefer).

After install, **restart Claude Desktop** to pick up the MCP server. Flipbook tools work in the regular **chat** tab.

If anything looks off, run `scripts\doctor.bat` — it checks every piece (database, MCP, Tailscale, firewall, power, server) and tells you exactly what's wrong.

---

## Daily use

The three tabs:

- **Bench**: three lists in one view —
  - *On the bench* — open follow-ups due today or overdue. Tap **✓ Done** when handled (or just log a new interaction with the contact, which auto-closes the open promise).
  - *Coming up* — open follow-ups in the next 7 days, so Tuesday's call doesn't sneak up on you.
  - *Recent entries* — closed-loop activity in the last week (an audit trail of what you actually did).
- **Book**: the index. All cards, searchable, filterable by tag.
- **Intake**: drop in an Excel file. Also where you **download** the entire book as Excel for backup or to edit-and-reimport.

### From the web

`http://localhost:8765` from the laptop, or `http://<laptop-name>:8765` from any device on the Tailscale network.

### From Claude Desktop

Open the regular **chat** tab in Claude Desktop and just talk:

- *"What's on the bench today?"*
- *"Log a visit with Hansen at Byggvarehuset. Showed him the new Makita line. Follow up Tuesday."*
- *"Add a card: Lars at Drammen Maskin, +47 901 23 456, tag him oslo and dewalt."*
- *"Show me everything I know about Marit Solberg."*
- *"Who's tagged makita?"*

The web UI and Claude share the same data. Anything logged in conversation shows up in the browser instantly.

> **Cowork doesn't see Flipbook.** Cowork is a remote agentic environment — it can't reach a local MCP server running on your laptop. Use the regular Claude Desktop chat tab for the conversational flow, or the web UI in a phone browser. (If Cowork support ever matters, see `docs/v2_questions.md`.)

### Phone setup

1. Install Tailscale on the laptop and the phone (free for personal use).
2. Sign both into the same account.
3. On the phone, open `http://<laptop-name>:8765` in any browser.
4. Add to Home Screen for one-tap access.

The page is responsive. Works fine in the garage, one hand, no zooming.

---

## Intake from Excel

Drop a `.xlsx` file on the **Intake** tab. The intake recognises these column headers (case-insensitive, Norwegian and English):

| Field   | Recognised headers                                |
| ------- | ------------------------------------------------- |
| Name    | Name, Navn, Kontaktperson, Contact                |
| Firm    | Company, Firma, Bedrift, Selskap, Kunde, Customer |
| Role    | Role, Title, Rolle, Stilling, Tittel              |
| Phone   | Phone, Telefon, Tlf, Mobile, Mobil                |
| Email   | Email, E-mail, E-post, Epost, Mail                |
| Notes   | Notes, Notater, Notat, Kommentar, Comment         |
| Tags    | Tags, Tag, Etiketter, Merkelapp                   |

Re-running the same file is safe. Each row is hashed; rows already on file are skipped. Update the sheet and re-import to bring in only what's new.

There's a sample file at `sample_data/kunder.xlsx` for testing, plus a 50-row synthetic demo at `sample_data/demo_50.xlsx`.

### Export back out

The **Intake** tab has a `⤓ Download flipbook.xlsx` button that returns a two-sheet workbook (Contacts + Interactions). Use it as a regular backup, or to edit a batch of cards in Excel and re-import the same file — the row-hash dedupe means re-importing unchanged rows is a no-op.

---

## If something breaks

1. Run `scripts/repair.sh` (Mac) or `scripts\repair.bat` (Windows). Reinstalls dependencies and re-registers the MCP server. Does **not** touch data.
2. Restart Claude Desktop.
3. If still broken, copy the `crm.db` somewhere safe and ping Thordur.

Common things:

- **Web UI says "offline"**: the server isn't running. Run `start.sh` / `start.bat`.
- **Claude doesn't see Flipbook tools**: restart Claude Desktop after install. Check `Settings → Developer` for `tools-crm`.
- **Phone can't reach the laptop**: both devices on Tailscale? Using the laptop's tailnet hostname?

---

## What's in the box

```
flipbook/
├── app/                 FastAPI service + SQLite layer + CRUD
├── mcp/                 MCP server for Claude Desktop chat
├── web/                 Flipbook UI (Alpine.js, vendored locally — no CDN)
│   ├── index.html       The single page
│   ├── alpine.min.js    Vendored Alpine 3.14
│   ├── icon.svg         Favicon + Add-to-Home-Screen
│   └── manifest.json    PWA manifest
├── scripts/             install / start / repair / doctor (Mac + Windows)
├── sample_data/         demo .xlsx files for testing intake
├── docs/                v2_questions.md scoping interview
└── pyproject.toml       Dependencies
```

The web UI, REST API, and Claude all call the same Python functions in `app/crud.py`. Single source of truth, no drift between surfaces.

---

## v1 scope

Three tables: `contacts`, `interactions`, `import_log`. Tags as comma-separated strings. No deals, no pipeline, no products. Ship something useful in week one and let real usage decide what v2 needs.

Explicit non-goals in v1: a deals/stages pipeline, products catalog, multi-user sharing, and Cowork support. Each is a real feature worth shipping if Flip asks for it after using v1 — and *only* then. See `docs/v2_questions.md` for the scoping interview.

---

<sub>A poka-yoke production by Gervi Labs · 2026</sub>
