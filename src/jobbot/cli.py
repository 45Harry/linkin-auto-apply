"""The `jobbot` command line."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Settings
from .db import connect, transaction
from .logging_setup import setup_logging
from .migrate import migrate
from .repo import companies

log = logging.getLogger("jobbot.cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobbot", description="Hands off job intake")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("run", help="start the scheduler (what the container runs)")
    sub.add_parser("cycle", help="run one hourly cycle now")
    sub.add_parser("profile-refresh", help="regenerate criteria from the profile now")

    add_company = sub.add_parser("add-company", help="add a tracked company")
    add_company.add_argument("--name", required=True)
    add_company.add_argument(
        "--ats", default="none", choices=["none", "greenhouse", "lever", "ashby", "workable"]
    )
    add_company.add_argument("--token", default=None, help="the board token or slug")
    add_company.add_argument("--website", default=None)

    sub.add_parser("setup-gmail", help="run the Gmail OAuth flow once, on your Mac")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    setup_logging()
    settings = Settings()

    if args.command == "setup-gmail":
        return _setup_gmail(settings)

    conn = connect(settings.db_path)
    try:
        if args.command == "migrate":
            applied = migrate(conn)
            print(f"applied {len(applied)} migration(s): {', '.join(applied) or 'none'}")
        elif args.command == "add-company":
            with transaction(conn):
                company_id = companies.add(
                    conn,
                    name=args.name,
                    ats_type=args.ats,
                    ats_token=args.token,
                    website=args.website,
                )
            print(f"added company {company_id}: {args.name}")
        elif args.command == "cycle":
            from .cycle import hourly_cycle

            hourly_cycle(conn, settings)
        elif args.command == "profile-refresh":
            from .profile import run_profile_refresh

            result = run_profile_refresh(conn, settings)
            print(f"profile refresh ok={result.ok} {result.summary}")
            if result.error:
                print(f"error: {result.error}", file=sys.stderr)
                return 1
        elif args.command == "run":
            from .scheduler import run_scheduler

            run_scheduler(conn, settings)
    finally:
        conn.close()
    return 0


def _setup_gmail(settings: Settings) -> int:
    from . import gmail_client

    client_file = settings.resolved_oauth_client_file
    if client_file is None or not client_file.exists():
        print(
            f"OAuth client JSON not found. Set GOOGLE_OAUTH_CLIENT_FILE. Looked at: {client_file}",
            file=sys.stderr,
        )
        return 1
    token_file = settings.resolved_gmail_token_file
    creds = gmail_client.run_oauth_flow(client_file, token_file)
    address = gmail_client.my_address(creds)
    print(f"Gmail authorised for {address or 'the account'}.")
    print(f"Token written to {token_file} (copy it to the VM's data/secrets/ over scp).")
    return 0
