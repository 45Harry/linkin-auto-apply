# jobbot

Hands off job intake. It finds new jobs and hiring posts matching your profile,
never logs into your LinkedIn account, and hands every match to the next step as a
`ready` row in one SQLite database.

Sources, in order of when they land:

1. Career boards (Greenhouse today; Lever, Ashby, Workable next)
2. LinkedIn job alert emails (read from your Gmail)
3. LinkedIn notification emails (hiring posts)
4. Public web search through self hosted SearXNG, with a capped Brave fallback

This is the first build slice: the project skeleton, the full database schema, and
one Greenhouse board that reaches `ready`, plus the Gmail setup command and the
alert path.

## Run it

Fill `.env` (copy `.env.example`), then:

```bash
docker compose up -d --build
```

The `app` service runs one `hourly_cycle` at start and then every hour. It writes
`jobbot.sqlite3` and its secrets under the mounted `data` folder.

## Operate it

```bash
jobbot migrate                 # apply database migrations
jobbot add-company --name "GitLab" --ats greenhouse --token gitlab
jobbot cycle                   # run one hourly cycle now
jobbot run                     # start the scheduler (what the container runs)
jobbot setup-gmail             # run this on your Mac once, then copy the token to the VM
```

## Layout

| Path | What it holds |
|---|---|
| `src/jobbot/config.py` | every setting, loaded from the environment |
| `src/jobbot/db.py` | the SQLite connection (WAL, busy timeout) |
| `src/jobbot/migrations/` | versioned SQL, applied by `migrate.py` |
| `src/jobbot/sources/` | one adapter per source (Greenhouse to start) |
| `src/jobbot/repo/` | table level data access |
| `src/jobbot/health.py` | the failure and recovery streak |
| `src/jobbot/alerts.py` | Gmail send, with an ntfy fallback |
| `src/jobbot/cycle.py` | the hourly cycle and its steps |
