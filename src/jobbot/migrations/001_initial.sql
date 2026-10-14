-- 001 initial schema: the full job intake data model.

CREATE TABLE companies (
    id                INTEGER PRIMARY KEY,
    name              TEXT NOT NULL,
    website           TEXT,
    linkedin_url      TEXT,
    ats_type          TEXT NOT NULL DEFAULT 'none'
                      CHECK (ats_type IN ('greenhouse', 'lever', 'ashby', 'workable', 'none')),
    ats_token         TEXT,
    origin            TEXT NOT NULL
                      CHECK (origin IN ('nepal_list', 'manual', 'discovered')),
    linkedin_followed INTEGER NOT NULL DEFAULT 0,
    muted             INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_companies_ats ON companies (ats_type, ats_token)
    WHERE ats_token IS NOT NULL;
CREATE UNIQUE INDEX ux_companies_name ON companies (lower(name));

CREATE TABLE raw_items (
    id           INTEGER PRIMARY KEY,
    source       TEXT NOT NULL,
    external_id  TEXT NOT NULL,
    content      TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    parse_status TEXT NOT NULL
                 CHECK (parse_status IN ('pending', 'parsed', 'failed', 'not_job')),
    parsed_by    TEXT,
    error        TEXT,
    UNIQUE (source, external_id)
);

CREATE TABLE jobs (
    id                  INTEGER PRIMARY KEY,
    company_id          INTEGER REFERENCES companies (id),
    title               TEXT NOT NULL,
    location            TEXT,
    work_mode           TEXT
                        CHECK (work_mode IN ('remote', 'hybrid', 'onsite', 'unknown')),
    salary_min          INTEGER,
    salary_max          INTEGER,
    salary_currency     TEXT,
    seniority           TEXT
                        CHECK (seniority IN ('intern', 'junior', 'mid', 'senior', 'lead', 'unknown')),
    apply_method        TEXT
                        CHECK (apply_method IN ('easy_apply', 'ats_form', 'email', 'unknown')),
    apply_target        TEXT,
    canonical_url       TEXT,
    description         TEXT,
    posted_at           TEXT NOT NULL,
    posted_at_estimated INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL
                        CHECK (status IN ('new', 'ready', 'filtered', 'expired')),
    filter_reason       TEXT,
    dedupe_key          TEXT NOT NULL UNIQUE,
    match_hash          TEXT,
    missed_polls        INTEGER NOT NULL DEFAULT 0,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL
);

CREATE INDEX ix_jobs_status_posted ON jobs (status, posted_at);
CREATE INDEX ix_jobs_match_hash ON jobs (match_hash);
CREATE INDEX ix_jobs_canonical_url ON jobs (canonical_url);
CREATE INDEX ix_jobs_last_seen ON jobs (last_seen_at);
CREATE INDEX ix_jobs_company ON jobs (company_id);

CREATE TABLE sightings (
    id          INTEGER PRIMARY KEY,
    job_id      INTEGER NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    source      TEXT NOT NULL
                CHECK (source IN ('gmail_alert', 'gmail_notification', 'ats', 'search')),
    source_ref  TEXT NOT NULL,
    raw_item_id INTEGER REFERENCES raw_items (id) ON DELETE SET NULL,
    seen_at     TEXT NOT NULL,
    UNIQUE (source, source_ref)
);

CREATE INDEX ix_sightings_job ON sightings (job_id);

CREATE TABLE contacts (
    id           INTEGER PRIMARY KEY,
    job_id       INTEGER NOT NULL REFERENCES jobs (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    role         TEXT
                 CHECK (role IN ('post_author', 'hiring_manager', 'recruiter')),
    linkedin_url TEXT,
    email        TEXT,
    phone        TEXT
);

CREATE INDEX ix_contacts_job ON contacts (job_id);

CREATE TABLE source_health (
    source               TEXT PRIMARY KEY,
    status               TEXT NOT NULL CHECK (status IN ('ok', 'failing')),
    last_success_at      TEXT,
    last_error_at        TEXT,
    last_error           TEXT,
    alerted_at           TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    quota_used           INTEGER NOT NULL DEFAULT 0,
    quota_period         TEXT
);
