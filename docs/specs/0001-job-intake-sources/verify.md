# Verify: job intake · spec 0001 · updated 2026-10-14

_Steps derived from spec 0001 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. This file covers the first build slice (the foundation and tracer bullet). Later slices add their own steps._

## Commands

- [ ] `export DATA_DIR=$(mktemp -d) && jobbot migrate` → prints "applied 1 migration(s): 001_initial.sql" and creates `$DATA_DIR/jobbot.sqlite3` → AC-5
- [ ] `sqlite3 "$DATA_DIR/jobbot.sqlite3" 'PRAGMA journal_mode;'` → `wal` → AC-18
- [ ] `sqlite3 "$DATA_DIR/jobbot.sqlite3" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"` → companies, contacts, jobs, raw_items, schema_migrations, sightings, source_health → AC-5
- [ ] `jobbot add-company --name "GitLab" --ats greenhouse --token gitlab` → prints "added company 1: GitLab" → AC-3
- [ ] `jobbot cycle` → one JSON line with `"source": "ats"`, `"ok": true`, and a summary with `boards: 1`, `failed: 0`, and many `created` on the first run → AC-3, AC-20
- [ ] `sqlite3 "$DATA_DIR/jobbot.sqlite3" "SELECT status, COUNT(*) FROM jobs GROUP BY status;"` → two rows, `ready` and `expired`, no `new` and no `filtered` yet → AC-3, AC-20
- [ ] `jobbot cycle` a second time → summary shows `created: 0`; `SELECT COUNT(*) FROM sightings;` is unchanged → AC-5
- [ ] `docker compose config -q` → exit 0 → AC-18

## UI / manual

- [ ] Open one job's `apply_target` in a browser → it is the board URL `https://job-boards.greenhouse.io/gitlab/jobs/<id>` → AC-3
- [ ] Compare a stored `jobs.posted_at` with the board's `first_published` for that posting id (both in UTC) → equal, and `posted_at_estimated = 0` → AC-3 (value sourcing: posted_at)
- [ ] Add a company with `jobbot add-company --name X --ats none` then `jobbot cycle` → that company is never fetched, so it contributes no jobs → AC-13 (partial)
- [ ] Point a company at a bad board token (`--token does-not-exist-xyz`) and run `jobbot cycle` three times → the 3rd run sends exactly one alert (Gmail, or ntfy when Gmail is not set up), the 4th sends none; then fix the token and run once → one recovery alert → AC-15
- [ ] Leave the bad token in place for a 3rd dead fetch → `SELECT ats_type FROM companies WHERE id=?` becomes `none` for that company → AC-3
- [ ] Find a GitLab posting older than 14 days → its job is stored `expired`; a posting within 14 days is stored `ready` → AC-6 (partial, full date order lands in the next slice)
- [ ] With a small board, drop a posting upstream and run three cycles → that job becomes `expired`; bring it back within two cycles → `missed_polls` returns to 0 → AC-3
- [ ] Run `jobbot setup-gmail` on your Mac → a browser opens, you click Allow once, and `data/secrets/gmail_token.json` is written → AC-17

## AI parsing and Gmail sources slice

- [ ] `python -m pytest tests/test_intake_sources.py -q` → 16 passed, no network calls → AC-1, AC-2, AC-5, AC-6, AC-7, AC-8, AC-10
- [ ] `ruff check src tests` → "All checks passed!" → AC-1, AC-2, AC-6, AC-7, AC-8, AC-9, AC-10
- [ ] With a real Gmail token, `jobbot cycle` → the `gmail_alert` step summary has a `jobs` count above 0 and matches the postings in recent alert emails; the `gmail_notification` step is `ok: true` → AC-1
- [ ] `sqlite3 "$DATA_DIR/jobbot.sqlite3" "SELECT source_ref FROM sightings WHERE source='gmail_alert' LIMIT 5;"` → values look like `li:<id>` → AC-1
- [ ] Find a real alert posting that lacks a company or a location → after a cycle, its `raw_items` row has `parse_status='pending'`; with a provider up the next cycle sets `parsed_by` to the provider name → AC-8, AC-10
- [ ] A non-hiring notification email (for example "See who viewed your profile") → its `raw_items.parse_status='not_job'` and no job is created → AC-2
- [ ] A hiring notification → one job (with `apply_method='email'` when the post shows a contact email) and a `post_author` contact; the contact `email` appears verbatim in the post body, otherwise it is null → AC-2, AC-9
- [ ] Stop Ollama and leave all hosted keys blank, then run a cycle → no crash, pending rows stay `parse_status='pending'`; leave it failing for six hours → exactly one AI-chain alert → AC-10
- [ ] Take a posting older than 14 days from an alert email → its job is stored `expired` and never `ready` → AC-6, AC-7
- [ ] Confirm the date order on a real alert: a relative date like "3w ago" (or an alert with no per-posting date) gives `posted_at_estimated=1`; a notification with an activity id gives `posted_at_estimated=0` and the timestamp decoded from the id → AC-6

## Profile refresh slice

- [ ] `python -m pytest tests/test_profile_refresh.py -q` → 8 passed, no network or disk PDF → AC-11, AC-12
- [ ] Put your CV at `data/profile/cv.pdf`, set a hosted provider key, then `jobbot profile-refresh` → prints `ok=True` and writes `data/criteria.json` with `titles`, `keywords`, `locations`, `seniority`, `exclude_keywords`, `sources_hash`, `alert_set_hash`, `alerts_email_sent_for`, `generated_at`, `generated_by` → AC-11
- [ ] The first run sends one email "LinkedIn searches to save" listing up to ten links shaped `https://www.linkedin.com/jobs/search/?keywords=<title>&location=<location>&f_TPR=r86400`; run it again with nothing changed → no email → AC-12
- [ ] Edit the CV PDF and run again → criteria regenerate; when the set of titles and locations is unchanged, no email is sent → AC-11, AC-12
- [ ] Rename `cv.pdf` away and run → exactly one "no CV found" alert, role queries are skipped, company queries keep running → AC-11
- [ ] With no provider reachable, run once → it keeps the old `criteria.json` and reports `ok=False`; run again → it retries (the input hashes are only committed on success) → AC-11

## ATS board adapters slice

- [ ] `python -m pytest tests/test_ats_adapters.py -q` → 9 passed, no network calls → AC-3
- [ ] `jobbot add-company --name "Lever Demo" --ats lever --token leverdemo` then `jobbot cycle` → jobs appear with `posted_at` equal to the posting's `createdAt` (epoch milliseconds) and `posted_at_estimated = 0` → AC-3
- [ ] `jobbot add-company --name "OpenAI" --ats ashby --token openai` then `jobbot cycle` → jobs appear with `posted_at` from `publishedAt` → AC-3
- [ ] `jobbot add-company --name "ABM" --ats workable --token abm-careers` then `jobbot cycle` → jobs appear with `posted_at` from `published_on` (a date, so midnight UTC) and a location built from the `locations` array → AC-3
- [ ] For each of the three, point a company at a bad token (`--token does-not-exist-xyz`) and run `jobbot cycle` three times → one alert, and `ats_type` becomes `none` on the third run → AC-3, AC-15

## Acceptance-criteria coverage

- AC-3 covered by the add-company, cycle, status, board-death, and missed-poll steps · AC-5 covered by the migrate, table, and second-cycle steps · AC-15 covered by the three-failure and recovery steps · AC-17 covered by setup-gmail plus the cycle runs with no manual command · AC-18 covered by the journal mode and the compose check · AC-20 covered by the cycle status query.
- AC-1, AC-2, AC-6, AC-7, AC-8, AC-9, AC-10 covered by the AI parsing and Gmail sources slice steps.
- AC-11, AC-12 covered by the profile refresh slice steps.
- AC-3 covered by the foundation steps (Greenhouse) and the ATS board adapters slice steps (Lever, Ashby, Workable).
- Not yet covered here (later slices): AC-4, AC-13 (full), AC-14, AC-16, AC-19 (the Ollama model benchmark is still open; it needs a live Ollama and about twenty labelled samples).
