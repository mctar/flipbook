# v2 scoping interview

Ask these after he has used v1 for two or three weeks. Don't ask all of them. Ask the ones that aren't already obvious from his usage. The goal is to find out what v1 made easy that he didn't expect, and what's still missing.

## Usage reality

1. What did you wish you could do that you couldn't?
2. What did you stop doing manually because the CRM made it easy?
3. What did you keep doing in a notebook or another tool? Why didn't the CRM win there?
4. How often do you actually use it: every call, every day, every week?
5. Which surface do you reach for first: web, Claude conversation, or phone?

## Sales model

6. Do you think about deals as discrete things with stages, or is it more "ongoing relationship that occasionally produces an order"?
7. Do you quote prices? If yes, how: verbal, email, formal document?
8. Do you have territories or accounts assigned, or is it more opportunistic?
9. What does your sales manager ask you to report on?
10. Are there products you sell often enough that picking from a list would beat typing?

## Collaboration & data

11. Do you ever need to share a contact or note with a colleague?
12. Does anyone else need to see your activity (manager, sales ops)?
13. Where else does customer data live (ERP, your company's CRM, Outlook)? Do you wish those were connected?
14. Do you carry data between this CRM and anything else manually right now?

## Reliability

15. What's the one thing that, if it stopped working, would make you stop using it?
16. Have you lost data? Almost lost data? Worried about losing data?

## The big question

17. If you could only have one new thing in v2, what would it be?

---

## How to read the answers

**If "deals with stages" is the answer to #6:** v2 needs a `deals` table with stage, value, expected_close, and a Kanban view. This is real CRM territory.

**If "ongoing relationship" is the answer to #6:** v2 stays tag-driven and adds richer reporting (cohorts, frequency, last-touch) instead of a pipeline. This is the more common reality for field sales and resists the "abandoned Salesforce" failure mode.

**If quotes/products come up in #7 or #10:** add a `products` table and a quote-builder MCP tool. This compounds with import: if his company has a product list in Excel, that becomes the seed data.

**If sharing/manager visibility comes up in #11 or #12:** v1 was single-user and single-machine on purpose. v2 needs to either (a) push to a shared backend, or (b) sync to his employer's existing CRM. Option (b) is usually cheaper and more politically realistic.

**If #15 surfaces a fragility:** that's the v2 priority regardless of what else he asks for. Reliability beats features.

---

## Known v1 limit: Cowork can't see Flipbook

The MCP integration is **local stdio** — Claude Desktop spawns a Python process on Flip's laptop and talks to it over stdin/stdout. That works in Claude Desktop's regular chat tab, but **not in Cowork** (the agentic sidebar) because Cowork runs in a remote execution context and can't reach a process on the user's machine. Same reason it doesn't work on `claude.ai` in a phone browser.

If Flip ever asks for Cowork access, the path is:

1. Add an HTTPS-based MCP transport on top of the existing FastAPI service in `app/main.py` — the tool implementations already exist in `app/crud.py`, so it's a thin protocol adapter, not a rewrite.
2. Expose the FastAPI service to the public internet via Tailscale Funnel (free for one device) or a tiny VPS, with bearer-token auth.
3. Register the HTTPS endpoint as a custom connector at claude.com.

Don't do this preemptively. The local-stdio design keeps the data on Flip's laptop and avoids hosting, auth, and an account model — all real costs. Only worth it if he genuinely wants to manage contacts from a coffee shop without the laptop, and he can't just open the web UI on his phone.
