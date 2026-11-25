"""M3a - a database belongs to exactly one source; live and demo must never share a file."""
import hashlib
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from config import Settings, default_database_url
from database import Base, Contract, Quote, SCHEMA_VERSION, Database, Meta, SourceMismatchError
from demo_collector import DemoCollector
from main import create_app


def make_db() -> Database:
    return Database("sqlite://")


def make_legacy_database(path) -> str:
    """A database as it looked before M3a: contracts and quotes, no meta table."""
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[Contract.__table__, Quote.__table__])
    with Session(engine) as session, session.begin():
        session.add(
            Contract(
                ins_code="X",
                symbol="X",
                name="",
                option_type="call",
                underlying_code="U",
                underlying_symbol="U",
                strike=1.0,
                expiry=date(2026, 12, 1),
                contract_size=1000,
            )
        )
        session.add(Quote(ins_code="X", ts=datetime(2026, 11, 1, 10, 0), last=1.0, bid=1.0, ask=2.0, volume=10))
    engine.dispose()
    return url


def meta_keys(db: Database) -> set[str]:
    with db.engine.connect() as conn:
        return {row[0] for row in conn.execute(text("SELECT key FROM meta"))}


def schema_snapshot(db: Database) -> list[tuple]:
    with db.engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(text("SELECT type, name, sql FROM sqlite_master ORDER BY type, name"))
        ]


# -- schema is created only after the source is accepted ------------------------------
def test_a_fresh_database_has_no_tables_until_the_source_is_accepted():
    db = make_db()
    assert db.has_table("contracts") is False
    assert db.has_table("quotes") is False
    assert db.has_table("meta") is False
    db.ensure_source("live")
    assert db.has_table("contracts") and db.has_table("quotes") and db.has_table("meta")


def test_empty_database_is_tagged():
    db = make_db()
    db.ensure_source("live")
    assert db.get_meta("source") == "live"
    assert db.get_meta("schema_version") == str(SCHEMA_VERSION)


def test_the_same_source_is_idempotent():
    db = make_db()
    db.ensure_source("demo")
    db.ensure_source("demo")  # second start on the same file
    assert db.get_meta("source") == "demo"


# -- refusals --------------------------------------------------------------------------
def test_another_source_is_refused():
    db = make_db()
    db.ensure_source("demo")
    with pytest.raises(SourceMismatchError) as exc:
        db.ensure_source("live")
    assert "demo" in str(exc.value) and "live" in str(exc.value)


def test_a_refused_legacy_database_is_left_structurally_untouched(tmp_path):
    path = tmp_path / "legacy.db"
    url = make_legacy_database(path)
    digest_before = hashlib.sha256(path.read_bytes()).hexdigest()

    db = Database(url)
    before = schema_snapshot(db)
    assert "meta" not in {name for _type, name, _sql in before}

    with pytest.raises(SourceMismatchError) as exc:
        db.ensure_source("live")
    assert "no source tag" in str(exc.value)

    assert schema_snapshot(db) == before          # same tables, same SQL
    assert db.has_table("meta") is False          # the tag table was not even created
    db.engine.dispose()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest_before  # same bytes


def test_an_unknown_source_is_refused():
    with pytest.raises(SourceMismatchError):
        make_db().ensure_source("lve")


def test_a_version_mismatch_does_not_create_missing_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    db = Database(url)
    db.ensure_source("live")
    with db.engine.begin() as conn:
        conn.execute(text("DROP TABLE quotes"))
        conn.execute(text("UPDATE meta SET value='999' WHERE key='schema_version'"))

    with pytest.raises(SourceMismatchError):
        db.ensure_source("live")
    assert db.has_table("quotes") is False  # refused before touching the schema


# -- meta table ------------------------------------------------------------------------
def test_meta_holds_exactly_the_expected_keys():
    db = make_db()
    db.ensure_source("demo")
    assert meta_keys(db) == {"source", "schema_version"}


def test_an_unsupported_schema_version_is_refused():
    db = make_db()
    db.ensure_source("live")
    with Session(db.engine) as session, session.begin():
        session.get(Meta, "schema_version").value = "999"
    with pytest.raises(SourceMismatchError):
        db.ensure_source("live")


# -- configuration and startup ---------------------------------------------------------
def test_default_database_url_follows_the_source(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPTIONS_SOURCE", "demo")
    assert default_database_url() == "sqlite:///./options_demo.db"
    monkeypatch.setenv("OPTIONS_SOURCE", "live")
    assert default_database_url() == "sqlite:///./options_live.db"


def test_the_app_refuses_to_start_on_a_database_of_another_source(tmp_path):
    url = f"sqlite:///{tmp_path / 'mixed.db'}"
    db = Database(url)
    db.ensure_source("demo")
    db.engine.dispose()

    cfg = Settings(source="live", database_url=url, redis_url="")
    with pytest.raises(SourceMismatchError):
        with TestClient(create_app(cfg, collector=DemoCollector(cfg))):
            pass
