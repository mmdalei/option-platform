"""M3a - a database belongs to exactly one source; live and demo must never share a file."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import Settings, default_database_url
from database import Contract, SCHEMA_VERSION, Database, Meta, SourceMismatchError
from demo_collector import DemoCollector
from main import create_app


def make_db() -> Database:
    return Database("sqlite://")


def meta_keys(db: Database) -> set[str]:
    with db.engine.connect() as conn:
        return {row[0] for row in conn.execute(text("SELECT key FROM meta"))}


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


def test_another_source_is_refused():
    db = make_db()
    db.ensure_source("demo")
    with pytest.raises(SourceMismatchError) as exc:
        db.ensure_source("live")
    assert "demo" in str(exc.value) and "live" in str(exc.value)


def test_a_legacy_database_with_rows_and_no_tag_is_refused():
    db = make_db()
    with Session(db.engine) as session, session.begin():
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
    with pytest.raises(SourceMismatchError) as exc:
        db.ensure_source("live")
    assert "no source tag" in str(exc.value)
    assert db.get_meta("source") is None  # refused: nothing was written


def test_an_unknown_source_is_refused():
    with pytest.raises(SourceMismatchError):
        make_db().ensure_source("lve")


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
