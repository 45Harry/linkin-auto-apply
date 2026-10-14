# 0001. Job intake from LinkedIn emails, career boards, and web search

**Date**: 2026-10-14
**Status**: In Progress

## Summary

This spec decides how the system finds new jobs and hiring posts automatically, every hour, without ever logging into your LinkedIn account and without paying for data. It reads the LinkedIn job alert and notification emails that already land in your Gmail, polls the free public job feeds of company career boards (including the Nepal tech companies list), and searches public LinkedIn posts through a self hosted search engine. An AI parser (a local model first, paid models only as fallback) turns messy text into clean job records, which the later matching step picks up. After a one time setup of about 15 minutes, it runs hands off.

## Rationale

Reasoning, options, and sources: see [rationale.md](rationale.md).

## Requirements

**User stories**:
- As a job seeker, I want every relevant new job and hiring post to reach my system within about an hour, so that I apply early without scrolling LinkedIn myself.
- As a job seeker, I want my LinkedIn account never touched by automation, so that I never risk a restriction or ban.
- As a job seeker, I want the system to learn what I'm looking for from my CV, GitHub, and LinkedIn profile, so that I don't maintain search settings by hand.
- As a job seeker, I want to be told once when something breaks (and once when it recovers), so that silent failures never cost me weeks of missed jobs.

**Acceptance criteria**:
- **AC-1**: Every LinkedIn job alert email received in the last 15 days is parsed on the next hourly run (all result pages read) into one job per listed posting, each with a sighting (`source = gmail_alert`, `source_ref` = `li:<LinkedIn job id>`, the id taken from `/jobs/view/(\d+)` so tracking parameters never vary it).
- **AC-2**: LinkedIn notification emails about posts are parsed; a post classified as a hiring post becomes a job with the post author stored as a contact (`role = post_author`); a non hiring post leaves its raw item at `parse_status = not_job` and creates no job.
- **AC-3**: Every company that is not muted and has `ats_type` other than `none` has its public career board polled hourly; each new posting becomes a job whose `posted_at` comes from the board's first published date (Greenhouse `first_published`, Lever `createdAt`, Ashby `publishedAt`, Workable `published_on`; if absent, `first_seen_at` with `posted_at_estimated = 1`). A job missing from its board for 3 polls in a row becomes `expired`.
- **AC-4**: Each hour, the search source runs the next 2 queries from a rotation of role queries (from the criteria) and per company queries (for every tracked company), limited to results from the past month. SearXNG is tried first; Brave is used only when SearXNG returns an HTTP error, times out, or reports all its engines unresponsive (an empty result is a valid answer, not a trigger); Brave usage never exceeds `BRAVE_MONTHLY_CAP` queries in a calendar month. Each result becomes one raw item keyed by its normalized post URL.
- **AC-5**: A job seen through several sources is stored as exactly one job row with one sighting per source; seeing the same `(source, source_ref)` again creates no new sighting and no new job, only updates `jobs.last_seen_at`. When sources disagree on a field, precedence is career board, then alert email, then notification email, then search; a later source only fills fields that are still null. Hiring posts with no known company are never merged by title alone.
- **AC-6**: A job whose `posted_at` is more than 14 days before now is stored with `status = expired` and is never set to `ready`; a `ready` or `new` job becomes `expired` once it crosses 14 days. Date sources, in order: the exact date in the source (board field, or the timestamp inside a LinkedIn post's activity id); the search result's own date (Brave `page_age`, SearXNG `publishedDate`); a relative date in the text ("1w", "3 days ago") converted against the source's own timestamp (Gmail `internalDate`, or the search `fetched_at`); for an alert email, its `internalDate`; failing all, `first_seen_at`. Every fallback after the search result's date sets `posted_at_estimated = 1`.
- **AC-7**: The light filter sets `status = filtered` with a `filter_reason` (`not_hiring` for an item first parsed as a job and then classified as not hiring, `exclude_keyword` for an exclude keyword matched case insensitively on whole words in the title or company name); every other parsed job within 14 days is set to `ready`. Age is handled only by `expired` (AC-6).
- **AC-8**: `work_mode`, salary range, `seniority`, `apply_method`, and `apply_target` are filled when the source states them, and left null (or `unknown` for enums) otherwise; nothing is invented.
- **AC-9**: Contacts store only details published in the source itself (name, LinkedIn profile URL, and email or phone only if they appear in the post or listing); no guessed or enriched emails are stored.
- **AC-10**: AI parsing tries providers in order Ollama, Claude, Grok, Gemini; a provider is skipped on error, timeout, or output that fails schema validation. If all fail, the raw item stays `pending` and is retried each hourly run until it ages past 14 days. If every provider has failed for more than 6 hours (counted from container start when there was never a success), one alert is sent. Hosted providers (Claude, Grok, Gemini) together make at most `AI_HOSTED_DAILY_CAP` calls per day in `TZ`; when the cap is hit, items wait as `pending` and one alert is sent.
- **AC-11**: Search criteria (titles, keywords, locations, seniority, exclude keywords) are generated automatically from the CV PDF, the LinkedIn profile PDF, and the public GitHub profile, on first start and whenever either PDF changes or the weekly GitHub refresh finds changes, with no manual confirm step. Generation uses the provider order Claude, Grok, Gemini, then Ollama (a small local model is weak at this), at temperature 0. If no CV exists, an alert is sent and only the role queries are skipped; company queries and every other source keep running.
- **AC-12**: After criteria are first generated, and again only when the normalized, sorted set of titles or locations changes, one email lists at most 10 LinkedIn job searches as ready links (`https://www.linkedin.com/jobs/search/?keywords=<title>&location=<location>&f_TPR=r86400`), each with the instruction "open, set alert, daily".
- **AC-13**: The Nepal tech companies list is imported on first start and synced weekly; new companies are added with `origin = nepal_list`. A career board is attached to a company only when a Greenhouse, Lever, Ashby, or Workable board link is found on that company's own website or careers page; board slugs are never guessed.
- **AC-14**: When a job's apply link (from a post, search result, or listing) points to a Greenhouse, Lever, Ashby, or Workable board of an untracked company, that company is added with `origin = discovered` and polled from the next run. Its name comes from the board API when available, else the parsed company name, else the board token. A weekly email lists the companies discovered in the past 7 days.
- **AC-15**: A source counts as failing after 3 consecutive failed runs and as recovered on its first success; exactly one alert email is sent on failing and one on recovery, no repeats in between. The `ats` source fails only when more than half of its boards error in a run (one dead board follows the AC-3 path). A search with no results is not a failure. If sending through Gmail fails, the alert goes to the ntfy topic instead.
- **AC-16**: A daily purge deletes jobs (with their sightings and contacts) whose `last_seen_at` is more than 30 days old, and raw items whose `fetched_at` is more than 30 days old; companies and source health rows are never purged.
- **AC-17**: After the one time setup (fill `.env`, click Allow for Gmail once, save the suggested LinkedIn alerts), the system runs with no manual commands and restarts by itself after a VM reboot.
- **AC-18**: From the internet, only SSH with key authentication is reachable; Ollama and SearXNG listen only on the internal Docker network; secret files are readable only by the app user.
- **AC-19**: VM memory use (MemTotal minus MemAvailable) stays above Oracle's 20% idle threshold through models kept resident in Ollama, sized so the total stays at or above 30% of RAM; a daily check sends an alert if memory use was below 25% for more than 5% of the past 24 hours.
- **AC-20**: Jobs with `status = ready` in the shared SQLite database are the handoff contract for the matching step; intake never scores fit.

## Decision

**Chosen option**: Option 3: Legitimate feeds only (Gmail, public career boards, self hosted web search) with a local first AI parser.

The system gathers jobs only from data you already receive or that is public, never from a session logged into LinkedIn, and runs as one Python service plus Ollama and SearXNG in Docker Compose on an Oracle Always Free VM.

**Implementation skills**: `docker-project-foundations` (`docker/skills`, `.claude/skills/docker-project-foundations/`) · `docker-compose-patterns` (`docker/skills`, `.claude/skills/docker-compose-patterns/`) · `docker-build-strategies` (`docker/skills`, `.claude/skills/docker-build-strategies/`) · `pydantic` (`pydantic/skills`, `.claude/skills/pydantic/`) · `searxng-search` (`ypares/agent-skills`, `.claude/skills/searxng-search/`) · `oci` (`oracle/skills`, `.claude/skills/oci/`)

## Feature design

**Stack** (chosen in the design conversation):

| Layer | Choice | Note |
|---|---|---|
| Language | Python 3.12+ | Pydantic for config and AI output validation |
| Database | SQLite (WAL mode, a journaling mode that lets reads run during writes) | One file on a mounted volume; single writer process |
| Scheduler | APScheduler inside the one app container | Jobs never overlap per source (max one instance each) |
| AI access | Own small router: Anthropic SDK for Claude, OpenAI SDK pointed at the OpenAI compatible endpoints of Ollama, xAI, and Gemini | Order: Ollama, Claude, Grok, Gemini |
| Search | SearXNG (self hosted, internal only) then Brave Search API (capped) | Brave only on SearXNG error or empty result |
| Gmail | Gmail API, scopes `gmail.readonly` and `gmail.send` only | OAuth app set to "In production" so tokens don't expire after 7 days |
| Deploy | Docker Compose: `app`, `ollama`, `searxng` | `restart: unless-stopped`; data and secrets on a mounted volume |
| Hosting | Oracle Cloud Always Free, Ampere A1 (2 OCPU, 12 GB RAM) | Keep alive via a resident Ollama model (see invariants) |
| Backup alerts | ntfy push topic | Used only when Gmail sending fails |
| Timezone | `Asia/Kathmandu` for all date logic and emails; timestamps stored in UTC | |

**Data model sketch** (confirmed in the design conversation, with one flagged addition):

- **companies**: `id` INTEGER PK; `name` TEXT NOT NULL; `website` TEXT NULL; `linkedin_url` TEXT NULL; `ats_type` TEXT NOT NULL CHECK in (`greenhouse`, `lever`, `ashby`, `workable`, `none`) default `none`; `ats_token` TEXT NULL; `origin` TEXT NOT NULL CHECK in (`nepal_list`, `manual`, `discovered`); `linkedin_followed` INTEGER NOT NULL default 0; `muted` INTEGER NOT NULL default 0; `created_at` TEXT NOT NULL. UNIQUE (`ats_type`, `ats_token`) where `ats_token` is not null; UNIQUE on `lower(name)`. Never purged.
- **jobs**: `id` INTEGER PK; `company_id` FK → companies NULL (a post may name no company); `title` TEXT NOT NULL; `location` TEXT NULL; `work_mode` TEXT CHECK in (`remote`, `hybrid`, `onsite`, `unknown`); `salary_min` INTEGER NULL; `salary_max` INTEGER NULL; `salary_currency` TEXT NULL; `seniority` TEXT CHECK in (`intern`, `junior`, `mid`, `senior`, `lead`, `unknown`); `apply_method` TEXT CHECK in (`easy_apply`, `ats_form`, `email`, `unknown`); `apply_target` TEXT NULL (URL or email); `canonical_url` TEXT NULL; `description` TEXT NULL; `posted_at` TEXT NOT NULL; `posted_at_estimated` INTEGER NOT NULL default 0; `status` TEXT NOT NULL CHECK in (`new`, `ready`, `filtered`, `expired`); `filter_reason` TEXT NULL; `dedupe_key` TEXT NOT NULL UNIQUE; `match_hash` TEXT NULL (set only when a company is known); `missed_polls` INTEGER NOT NULL default 0 (career board jobs only); `first_seen_at` TEXT NOT NULL; `last_seen_at` TEXT NOT NULL. Indexes on (`status`, `posted_at`), `match_hash`, `canonical_url`, `last_seen_at`.
- **sightings**: `id` INTEGER PK; `job_id` FK → jobs NOT NULL (ON DELETE CASCADE); `source` TEXT NOT NULL CHECK in (`gmail_alert`, `gmail_notification`, `ats`, `search`); `source_ref` TEXT NOT NULL; `raw_item_id` FK → raw_items NULL (ON DELETE SET NULL); `seen_at` TEXT NOT NULL. UNIQUE (`source`, `source_ref`).
- **raw_items**: `id` INTEGER PK; `source` TEXT NOT NULL; `external_id` TEXT NOT NULL; `content` TEXT NOT NULL; `fetched_at` TEXT NOT NULL; `parse_status` TEXT NOT NULL CHECK in (`pending`, `parsed`, `failed`, `not_job`); `parsed_by` TEXT NULL (`ollama`, `claude`, `grok`, `gemini`, `rules`); `error` TEXT NULL. UNIQUE (`source`, `external_id`).
- **contacts**: `id` INTEGER PK; `job_id` FK → jobs NOT NULL (ON DELETE CASCADE); `name` TEXT NOT NULL; `role` TEXT CHECK in (`post_author`, `hiring_manager`, `recruiter`); `linkedin_url` TEXT NULL; `email` TEXT NULL; `phone` TEXT NULL.
- **source_health**: `source` TEXT PK (e.g. `gmail_alert`, `gmail_notification`, `ats`, `search_searxng`, `search_brave`, `ai_chain`, `nepal_list`, `profile`); `status` TEXT NOT NULL CHECK in (`ok`, `failing`); `last_success_at` TEXT NULL; `last_error_at` TEXT NULL; `last_error` TEXT NULL; `alerted_at` TEXT NULL; `consecutive_failures` INTEGER NOT NULL default 0; `quota_used` INTEGER NOT NULL default 0 and `quota_period` TEXT NULL (`YYYY-MM` for `search_brave`, `YYYY-MM-DD` for `ai_hosted`), which enforce the Brave monthly cap (AC-4) and the hosted AI daily cap (AC-10).

Additions beyond the model you confirmed (from the design conversation and the cross check): `jobs.match_hash`, `jobs.missed_polls`, `source_health.consecutive_failures`, `source_health.quota_used`, `source_health.quota_period`.

Relationships: company 1 to many jobs; job 1 to many sightings; job 1 to many contacts; raw item 1 to many sightings (one alert email lists several jobs). One migration creates all tables.

**Dedupe and merge** (how AC-5 works):
- `dedupe_key` for a new job: career board posting `ats:<ats_type>:<ats_token>:<posting id>`; LinkedIn job `li:<job id from /jobs/view/(\d+)>`; LinkedIn post `post:<activity id>`; anything else `url:<normalized canonical URL>`.
- `match_hash` (only when a company is known): sha256 of normalized company + normalized title + city. Normalizing: lowercase, strip punctuation, drop legal suffixes (`pvt`, `ltd`, `private`, `limited`, `inc`, `llc`), collapse spaces; city is the first comma separated token of the location ("Kathmandu, Bagmati, Nepal" becomes `kathmandu`; remote becomes `remote`).
- Lookup order for an incoming item: `dedupe_key`, then `canonical_url`, then `match_hash`. A hit merges (new sighting, contact, null fields filled by the precedence in AC-5); a miss creates a job. Posts without a known company never use `match_hash`, so different authors' "Software Engineer" posts stay separate.
- Post dates: a LinkedIn activity id (in `urn:li:activity:<id>` or the post URL) holds a millisecond timestamp in its top 41 bits, so `posted_at = (id >> 22)` milliseconds since 1970, exact (not estimated).

**State transitions** (job):
- `new` (created, parse complete) → `ready` (passes the light filter, within 14 days)
- `new` → `filtered` (not a hiring post, or exclude keyword)
- `new` / `ready` → `expired` (`posted_at` older than 14 days, checked at intake and by the hourly expiry pass; or a career board job missing from its board for 3 polls in a row)
- `expired` and `filtered` are terminal. Deletion happens only through the 30 day purge.

Raw item: `pending` → `parsed` | `not_job` | `failed` (only once older than 14 days with every provider failing); `pending` stays `pending` across retries.

**Interface surface** (no HTTP API; the system is scheduled jobs plus a one time setup command):

| Job / command | Trigger | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `hourly_cycle` | hourly (one APScheduler job, max one instance) | none | runs the steps below in order, each step isolated so one failing step never stops the next | none | step errors recorded per source in `source_health` |
| step 1 `gmail_alerts` | `hourly_cycle` | Gmail query `from:(jobalerts-noreply@linkedin.com OR jobs-listings@linkedin.com) newer_than:15d`, all pages (verify senders on real emails) | raw_items, jobs, sightings | Gmail OAuth token | token revoked → health alert via ntfy; parse failure → raw stays pending |
| step 2 `gmail_notifications` | `hourly_cycle` | Gmail query `from:notifications-noreply@linkedin.com newer_than:15d`, all pages (verify sender) | raw_items, jobs, contacts, sightings | Gmail OAuth token | same as above; these emails often carry only a snippet, so classify from snippet plus URL and expect many `not_job` |
| step 3 `ats_boards` | `hourly_cycle` | companies where `ats_type != none` and `muted = 0` | jobs, sightings, `missed_polls` | none (public feeds) | 404 board 3 polls in a row → set company `ats_type = none`, note in weekly digest; timeout → retry next run |
| step 4 `web_search` | `hourly_cycle` | 2 queries from the rotation; criteria; companies; time range past month | raw_items, jobs, contacts, sightings | Brave key (fallback only) | SearXNG error, timeout, or all engines unresponsive → Brave; Brave cap reached → skip until next month, one alert |
| step 5 `parse_pending` | `hourly_cycle` | raw_items where `parse_status = pending` | parsed jobs | provider keys | all providers fail or hosted cap reached → stays pending (AC-10) |
| step 6 `expire_and_filter` | `hourly_cycle` | jobs in `new` / `ready` | status changes | none | none |
| `profile_refresh` | on start, on file change (hash checked hourly), weekly for GitHub | `data/profile/cv.pdf`, `data/profile/linkedin.pdf`, GitHub username | `data/criteria.json`; LinkedIn alerts email when the title or location set changes | GitHub token optional | no CV → alert, role queries skipped |
| `nepal_list_sync` | on start, weekly | `NEPAL_LIST_URL` (raw README) | companies; board detection by scanning each company website and its careers page for board links | none | format change → health alert, keep existing companies; website unreachable → no board, retried next week |
| `weekly_digest` | weekly (Monday 09:00 Asia/Kathmandu) | companies discovered in the past 7 days, boards marked dead | one email | Gmail send | send failure → ntfy |
| `purge` | daily 03:00 Asia/Kathmandu | 30 day cutoff | deletes | none | none |
| `vm_health` | daily | memory use samples (taken every 10 minutes) | alert if under 25% | none | none |
| `jobbot setup-gmail` | once, by you, **on your Mac** (the VM has no browser for the OAuth redirect) | Google OAuth client JSON | `gmail_token.json`, which you copy to the VM's `data/secrets/` over SSH (`scp`) | your one Allow click | none |

SQLite runs with `busy_timeout` set (5 seconds) so the daily and weekly jobs wait instead of failing while `hourly_cycle` writes.

**`data/criteria.json` shape**: `titles` (list of strings), `keywords` (list), `locations` (list, including `remote` when wanted), `seniority` (list of the job seniority values), `exclude_keywords` (list), `sources_hash` (hash of both PDFs plus the GitHub snapshot), `alert_set_hash` (hash of the normalized, sorted titles and locations), `alerts_email_sent_for` (the `alert_set_hash` last emailed), `generated_at`, `generated_by` (provider).

**Search rotation**: the query list is role queries (`site:linkedin.com/posts hiring "<title>" <location>` for each title and location in the criteria) followed by company queries (`site:linkedin.com/posts "<company name>" hiring` for each tracked company). The hour's 2 queries are positions `(2 × hours since 1970) mod N` and the next one, so the rotation needs no stored cursor and resumes correctly after downtime. Every query is limited to the past month (SearXNG `time_range=month`, Brave `freshness=pm`). SearXNG is pinned to engines that support `site:` and tolerate a datacenter IP (start with Brave, DuckDuckGo, and Startpage, and keep only those that pass a test during the build).

**Value sourcing**:

| Action | Value produced / displayed | Source |
|---|---|---|
| Any job create | `posted_at` | The AC-6 order: board field (`first_published`, `createdAt`, `publishedAt`, `published_on`) or LinkedIn activity id timestamp; search result date (`page_age`, `publishedDate`); relative text converted against Gmail `internalDate` or search `fetched_at`; alert email `internalDate`; `first_seen_at` |
| Job merge | which value wins per field | Source precedence in AC-5 (board, alert, notification, search); later sources fill nulls only |
| Board job expiry | polls missed | `jobs.missed_polls`, reset to 0 whenever the posting is seen |
| 14 day rule | "now" and day boundaries | System clock in UTC, evaluated in `TZ` (`Asia/Kathmandu`) |
| Job create | `company_id` | Matched by ATS token, then by normalized name against companies; created with `origin = discovered` only for ATS links (AC-14), else left null |
| Discovered company | `name` | Board API name (e.g. the Greenhouse board name) when available; else the parsed company; else the board token |
| Company board | `ats_type`, `ats_token` | Board links found on the company's own website or careers page (AC-13), or a job's apply link (AC-14); never guessed |
| Job create | `work_mode`, salary, `seniority`, `apply_method`, `apply_target` | AI parser output validated by the Pydantic `ParsedJob` schema; ATS fields where the board provides them; null or `unknown` when absent |
| Job create | `dedupe_key`, `match_hash` | Derived per the dedupe and merge rule above |
| Contact create | name, profile URL, email, phone | Only the text of the source item (AC-9) |
| Search rotation | the queries | `data/criteria.json` (titles, locations) plus companies table |
| Brave cap | queries used this month | `source_health.quota_used` and `quota_period` for `search_brave`, reset when the month changes in `TZ` |
| Criteria | titles, keywords, locations, seniority, excludes | AI over the text of `cv.pdf`, `linkedin.pdf`, and the GitHub API (public repos, languages, bio) |
| Criteria change detection | file hashes and GitHub snapshot hash | `sources_hash` in `data/criteria.json` |
| LinkedIn alerts email | whether to send, and the links | Sent when `alert_set_hash` differs from `alerts_email_sent_for`; links built from up to 10 title and location pairs, titles first |
| Hosted AI cap | calls made today | `source_health` row `ai_hosted`, `quota_used` with `quota_period = YYYY-MM-DD` in `TZ` |
| Failing / recovered | run streak | `source_health.consecutive_failures` (failing at 3, reset on success) |
| Alert emails | recipient | `ALERT_EMAIL_TO`, default the authenticated Gmail address |
| Source alerts | "already alerted" | `source_health.status` and `alerted_at` |
| AI chain 6 hour alert | how long all providers failed | `source_health` row `ai_chain`, `last_success_at`, or the container start time when it is null |
| Weekly digest | discovered companies | `companies.created_at` within 7 days and `origin = discovered` |
| Memory check | memory use percent | `(MemTotal − MemAvailable) / MemTotal` from the host `/proc/meminfo` (mounted read only), sampled every 10 minutes, kept in memory for 24 hours |

**Key invariants**:
- The system never authenticates to LinkedIn and never sends any request to linkedin.com while logged in as you. LinkedIn content enters only through Gmail and public search results.
- At most one job row per `dedupe_key`; at most one sighting per `(source, source_ref)`; at most one raw item per `(source, external_id)`. Writes use `INSERT ... ON CONFLICT` so every fetch job is safe to rerun (idempotent).
- A job with `posted_at` more than 14 days old is never `ready`.
- No contact email or phone exists unless it appears verbatim in its source item.
- Every AI output passes Pydantic validation before it touches the database; invalid output counts as a provider failure.
- Brave queries in a month never exceed `BRAVE_MONTHLY_CAP`; hosted AI calls in a day never exceed `AI_HOSTED_DAILY_CAP`.
- Only one app process writes SQLite; `hourly_cycle` never runs twice at once, and its steps run in a fixed order.
- A company's career board comes only from a link actually found, never from a guessed slug.
- Ollama models stay loaded (`OLLAMA_KEEP_ALIVE=-1`, `OLLAMA_MAX_LOADED_MODELS` sized to fit), holding memory use at or above 30% of RAM.

**Security model**:
- Single user system; no user accounts, no inbound API.
- Network: Oracle security list and host firewall allow only TCP 22; SSH keys only, password login off. `ollama` and `searxng` have no published ports.
- Secrets: `.env` and `data/secrets/` are mode 600, owned by the app user, mounted into the container, git ignored. No secret is stored in SQLite or logs.
- Gmail access is least privilege: `gmail.readonly` plus `gmail.send`; no modify or delete scope.
- Privacy: posts and emails contain other people's personal data (names, sometimes contacts). Storage is limited to what was published, and everything except companies is deleted after 30 days. The CV text is sent to a hosted AI provider only when Ollama falls back.
- Logs never contain email bodies, tokens, or API keys; they record ids and counts.

**Configuration required**:
- `TZ`: `Asia/Kathmandu`
- `DATA_DIR`: mounted data folder (SQLite file, profile PDFs, criteria, secrets)
- `GOOGLE_OAUTH_CLIENT_FILE`: path to the OAuth client JSON from your Google Cloud project (prerequisite: create the project, enable the Gmail API, set the consent screen to "In production")
- `GMAIL_TOKEN_FILE`: path to the token written by `jobbot setup-gmail`
- `ALERT_EMAIL_TO`: where alerts go (default the Gmail address itself)
- `NTFY_TOPIC`: private ntfy topic name for the backup alerts
- `OLLAMA_URL`, `OLLAMA_MODEL`: internal Ollama URL and the model picked by the benchmark task
- `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default `claude-haiku-5-5`; verify the current cheapest id)
- `XAI_API_KEY`, `GROK_MODEL` (default `grok-build-0.1`, the cheapest listed text model on 2026-10-14)
- `GEMINI_API_KEY`, `GEMINI_MODEL` (pick the current free tier Flash class model in AI Studio)
- `AI_ITEM_TIMEOUT_SECONDS`: per provider timeout, default 30 for Ollama, 20 for hosted
- `AI_HOSTED_DAILY_CAP`: default 200 calls per day across Claude, Grok, and Gemini
- `OLLAMA_RESIDENT_MODELS`: the model or models kept loaded to hold memory at or above 30% (set by the benchmark task)
- `SEARXNG_URL`: internal SearXNG URL
- `BRAVE_API_KEY`, `BRAVE_MONTHLY_CAP` (default 950, under the about 1,000 queries the $5 monthly credit covers)
- `SEARCH_QUERIES_PER_HOUR`: default 2
- `GITHUB_USERNAME`, `GITHUB_TOKEN` (optional; raises the API rate limit)
- `NEPAL_LIST_URL`: raw README URL of `mesaugat/tech-companies-in-nepal`
- `MAX_JOB_AGE_DAYS` (14), `RETENTION_DAYS` (30)

**Critical test scenarios**:
- Happy path: a recorded LinkedIn alert email with 5 postings yields 5 `ready` jobs, 5 sightings, raw item `parsed`, verifies **AC-1**, **AC-7**, **AC-8**
- Dedupe: the same role arrives through a LinkedIn alert (location "Kathmandu, Bagmati, Nepal"), a Greenhouse board ("Kathmandu", company "Acme Pvt. Ltd."), and a hiring post naming Acme; one job, three sightings, one contact, board fields win; rerunning all three sources changes nothing but `last_seen_at`, verifies **AC-5**, **AC-2**
- No false merge: two "Software Engineer" posts by different authors with no company stay two jobs, verifies **AC-5**
- Date rule: a post URL with activity id yields its exact date; a snippet saying "3w" fetched today yields `expired`; an alert email with no date uses its `internalDate` with `posted_at_estimated = 1`, verifies **AC-6**
- Board closure: a Greenhouse posting absent for 3 polls becomes `expired`; absent for 2 then back resets `missed_polls`, verifies **AC-3**
- Board detection: a Nepal list company whose website links to `jobs.lever.co/acme` gets `ats_type = lever`; a company without such a link stays `none` even if a same named board exists, verifies **AC-13**
- AI fallback: Ollama times out and Claude returns invalid JSON; Grok's valid output is stored with `parsed_by = grok`; with all four failing, the item stays `pending` and is parsed on the next run; at the hosted cap, items wait and one alert is sent, verifies **AC-10**
- Criteria stability: regenerating criteria with the same inputs, or a GitHub change that leaves titles and locations the same, sends no alerts email, verifies **AC-11**, **AC-12**
- Brave cap: an empty SearXNG result does not call Brave; with `quota_used` at the cap, a SearXNG error does not call Brave and sends one alert, verifies **AC-4**, **AC-15**
- Health alerts: 2 failed runs send nothing; the 3rd sends one email; the first success sends one recovery email; a Gmail send failure goes to ntfy; one dead board out of 20 does not mark `ats` failing, verifies **AC-15**
- Privacy: a post with an email in its text stores that email; a post without one stores a contact with a null email and no guessed address, verifies **AC-9**
- Purge: a job last seen 31 days ago is deleted; a job first seen 40 days ago but seen yesterday stays; companies stay, verifies **AC-16**
- Exposure: a port scan of the VM shows only 22 open; Ollama and SearXNG are unreachable from outside, verifies **AC-18**

## Build plan

Build approach: none recorded for this project, so this assumes **Tracer Bullet**: one thin path from a real source to a `ready` job first, then each source thickens it.

1. Scaffold the Python project, `compose.yaml` with `app`, `ollama`, `searxng` (internal network, no published ports, `restart: unless-stopped`, mounted `DATA_DIR`), Pydantic settings loading every variable above, JSON logging to stdout, `TZ` handling, satisfies **AC-17**, **AC-18**
2. Create the single migration for the full data model (including `match_hash`, `missed_polls`, `consecutive_failures`, `quota_used`, `quota_period`, and the indexes) with WAL mode and `busy_timeout`, satisfies **AC-5**, **AC-16**
3. Tracer bullet: confirm the Greenhouse public endpoint with a live request, then poll one hand added Greenhouse company inside the `hourly_cycle` job, upsert jobs and sightings with the dedupe and merge rule, take `first_published`, track `missed_polls`, set `ready`, satisfies **AC-3**, **AC-5**, **AC-20**
4. `jobbot setup-gmail` command (run on the Mac, token copied to the VM), Gmail send, `source_health` with the 3 failure streak, failure and recovery emails, ntfy backup, satisfies **AC-15**, **AC-17**
5. AI router (Ollama, Claude, Grok, Gemini) with Pydantic `ParsedJob` and `ParsedPost` schemas, timeouts, fallback, and the hosted daily cap; benchmark 2 or 3 small Ollama instruct models (about 1.5B to 4B, 4 bit) on 20 real samples, set `OLLAMA_MODEL` to the most accurate one under 30 seconds per item, and choose `OLLAMA_RESIDENT_MODELS` so resident memory reaches at least 30% of RAM, satisfies **AC-10**, **AC-19**
6. Gmail alerts source: 15 day query with paging, both senders, job id extraction, raw items, rules based extraction for the structured alert HTML with AI fallback, extra fields, satisfies **AC-1**, **AC-8**
7. Expiry and light filter pass (the full AC-6 date order including activity id timestamps, exclude keywords on whole words), satisfies **AC-6**, **AC-7**
8. Profile refresh: extract text from both PDFs, fetch GitHub profile, generate `data/criteria.json` with Claude first at temperature 0, set based change detection, LinkedIn alerts email with up to 10 ready links, missing CV alert, satisfies **AC-11**, **AC-12**
9. Remaining board adapters (Lever, Ashby, Workable; confirm each endpoint and its date field live first), Nepal list import and weekly sync with website based board detection, discovery from apply links with board API names, weekly digest email, satisfies **AC-3**, **AC-13**, **AC-14**
10. Gmail notifications source: hiring post classification from snippet plus URL, post author contacts, merge into matching jobs, satisfies **AC-2**, **AC-9**
11. Web search source: SearXNG configuration (JSON output, internal only, engines tested and pinned), stateless rotation, past month time range, Brave fallback on errors only with the monthly cap, one raw item per result, satisfies **AC-4**
12. Daily purge by `last_seen_at`, memory sampling and daily VM health check, satisfies **AC-16**, **AC-19**
13. Deploy to the Oracle VM: security list and host firewall to port 22 only, SSH keys only, file permissions, copy the Gmail token, first start, and a short `docs/runbook.md` for the one time setup, satisfies **AC-17**, **AC-18**

## Consequences

**Positive**:
- Your LinkedIn account carries zero automation risk.
- Running cost is near $0: Oracle Always Free, SearXNG, a free Gemini tier, and Ollama do most of the work; Claude and Grok are paid fallbacks used only when the free options fail.
- Every source sits behind the same raw item, parse, and upsert path, so adding a source later is one adapter.
- The `ready` status is a clean, testable contract for the matching spec.

**Negative / tradeoffs**:
- Coverage is partial: posts outside your network that search engines haven't indexed, and LinkedIn jobs you never get alerts for, are missed. That's the price of zero risk and zero cost.
- LinkedIn alert emails arrive at most daily, so LinkedIn sourced jobs are up to a day old even with hourly checks.
- SearXNG depends on upstream search engines that rate limit or block it; some hours will find nothing, and Brave needs a card on file.
- Parsers for LinkedIn email HTML break whenever LinkedIn changes its templates; the AI fallback softens this but costs more calls.
- The keep alive approach rests on Oracle's current idle policy and on keeping enough model memory resident (about 30% of RAM), which leaves less room for other work; a policy change could reclaim the VM.
- Notification emails usually carry only a snippet of a post, so that source yields fewer jobs than it might seem.
- Criteria are fully automatic with no confirm step, so a bad extraction silently narrows or widens the search until the next profile change.
- Small CPU only VM: the local model is slow (seconds per item), which caps throughput at a few hundred items per hour.

**Neutral**:
- LinkedIn job alerts must be saved by you once (the system emails you the exact searches); this is the only recurring human step, and only when criteria change.
- Endpoint shapes for Lever, Ashby, and Workable were not verified in this session; each build task confirms them live first.

## Follow-up

- [ ] Design next specs, each its own decision: (a) matching and fit scoring against your profile; (b) tailored CV generation per job from your CV, GitHub, and LinkedIn; (c) manager outreach email (finding the right person, address sourcing, sending from Gmail, deliverability, anti spam and privacy law); (d) whether and how to submit applications, with a strong suggestion of an approval step before anything is sent in your name.
- [ ] Before building, verify the LinkedIn sender addresses (`jobalerts-noreply@linkedin.com`, `jobs-listings@linkedin.com`, `notifications-noreply@linkedin.com`) against real emails in your inbox.
- [ ] Verify the current cheapest Claude model id and the Gemini free tier model and limits at build time.
- [ ] Optional MCP servers you chose for the build (you connect these in your Claude settings, e.g. `claude mcp add`): Gmail MCP (Google developer preview, verify on Google's page), a SearXNG MCP (community), and Docker MCP Gateway.
- [ ] No `AGENTS.md` exists yet. Run `/audit` to create it, so the stack, the six installed skills (`docker-project-foundations`, `docker-compose-patterns`, `docker-build-strategies`, `pydantic`, `searxng-search`, `oci`; all project wide, root level), and these MCP servers get recorded.
- [ ] No scope exists yet. Consider `/scope` to enroll this feature and the next specs above.
- [ ] Consider moving the Oracle account to Pay As You Go later if the keep alive approach ever fails (still $0 within free limits, and exempt from idle reclamation).
