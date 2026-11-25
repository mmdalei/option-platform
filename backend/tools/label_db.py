"""
label_db.py - tag an existing database with its source (milestone M3a).

It writes ONLY the `meta` table; contracts and quotes are never touched, and no
migration is run. Use it only when you are sure which source produced the data:

    python tools/label_db.py --source live --db sqlite:///./options.db --force

--force is required whenever the database already holds rows or carries a
different source tag: it is the explicit confirmation that you know what the
data is. Without it the tool refuses and exits with code 2.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from database import SCHEMA_VERSION, KNOWN_SOURCES, Database, Meta  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tag a database with its source. Writes only the meta table."
    )
    parser.add_argument("--source", required=True, choices=sorted(KNOWN_SOURCES))
    parser.add_argument("--db", default=None, help="Database URL (default: DATABASE_URL from .env)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Required when the database already holds rows or carries another source tag",
    )
    args = parser.parse_args()

    url = args.db or settings.database_url
    if url.startswith("sqlite:///"):
        path = Path(url[len("sqlite:///") :])
        if not path.exists():
            print(f"error: database not found: {path.resolve()}")
            return 2

    db = Database(url)
    try:
        stored = db.get_meta("source")
        contracts, quotes = db.row_counts()
        print(f"database      : {url}")
        print(f"contracts     : {contracts}")
        print(f"quotes        : {quotes}")
        print(f"stored source : {stored}")
        print(f"requested     : {args.source}")

        if stored == args.source and db.get_meta("schema_version") == str(SCHEMA_VERSION):
            print("already tagged with this source; nothing to do.")
            return 0

        needs_confirmation = (stored is not None and stored != args.source) or (
            stored is None and (contracts or quotes)
        )
        if needs_confirmation and not args.force:
            print("refusing: the database is not empty or carries another source tag.")
            print("Back it up, then re-run with --force if you are sure of the source.")
            return 2

        with Session(db.engine) as session, session.begin():
            session.merge(Meta(key="source", value=args.source))
            session.merge(Meta(key="schema_version", value=str(SCHEMA_VERSION)))
        print(f"tagged source={args.source!r}, schema_version={SCHEMA_VERSION}")
        print(f"make sure DATABASE_URL points at this file: {url}")
        return 0
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
