"""
database.py - persistent storage (SQLite by default, PostgreSQL via DATABASE_URL).

contracts  one row per option contract: static facts (strike, expiry, underlying ...)
quotes     time series of prices / open interest / IV. A row is written only when
           something changed since the previous row of that contract, so polling
           after the close does not fill the disk with duplicates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, create_engine, func, insert, inspect, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Contract(Base):
    __tablename__ = "contracts"

    ins_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128), default="")
    option_type: Mapped[str] = mapped_column(String(4))  # "call" | "put"
    underlying_code: Mapped[str] = mapped_column(String(64), index=True)
    underlying_symbol: Mapped[str] = mapped_column(String(64))
    strike: Mapped[float] = mapped_column(Float)
    expiry: Mapped[date] = mapped_column(Date, index=True)
    contract_size: Mapped[int] = mapped_column(Integer, default=1000)


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ins_code: Mapped[str] = mapped_column(String(64), ForeignKey("contracts.ins_code"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)  # naive UTC
    underlying_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last: Mapped[float | None] = mapped_column(Float, nullable=True)
    bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    iv: Mapped[float | None] = mapped_column(Float, nullable=True)
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)


class Meta(Base):
    """Key/value table: which source owns this database and which schema version it has."""

    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


SCHEMA_VERSION = 1
KNOWN_SOURCES = frozenset({"live", "demo", "replay"})  # replay arrives in M6


class SourceMismatchError(RuntimeError):
    """The database belongs to another source (or carries no tag). Startup must stop."""


class Database:
    def __init__(self, url: str) -> None:
        options: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}  # used from worker threads
            if url in ("sqlite://", "sqlite:///:memory:"):
                options["poolclass"] = StaticPool  # one shared connection for in-memory DBs
        self.engine = create_engine(url, **options)
        # Tables are NOT created here: a legacy database must stay byte-for-byte untouched
        # until ensure_source() has accepted it (M3a). Call create_schema() after the guard.
        self._known: set[str] = set()
        self._last_state: dict[str, tuple] = {}

    # -- source guard ----------------------------------------------------------
    def has_table(self, name: str) -> bool:
        return inspect(self.engine).has_table(name)

    def create_schema(self) -> None:
        """Create the tables that are missing. Only after ensure_source() accepted the database."""
        Base.metadata.create_all(self.engine)

    def get_meta(self, key: str) -> str | None:
        if not self.has_table(Meta.__tablename__):
            return None  # a database from before M3a has no meta table: it counts as untagged
        with Session(self.engine) as session:
            row = session.get(Meta, key)
        return None if row is None else row.value

    def row_counts(self) -> tuple[int, int]:
        """(contracts, quotes) - tells an empty database from a legacy one."""
        existing = {model.__tablename__: self.has_table(model.__tablename__) for model in (Contract, Quote)}
        counts = [0, 0]
        with Session(self.engine) as session:
            for i, model in enumerate((Contract, Quote)):
                if existing[model.__tablename__]:
                    counts[i] = int(session.execute(select(func.count()).select_from(model)).scalar_one())
        return counts[0], counts[1]

    def ensure_source(self, source: str) -> None:
        """
        Make sure this database belongs to `source` before anything is written to it.
        Nothing is created and nothing is written until the source has been accepted.

        no tag + empty database -> create the schema, then tag it (source and schema_version)
        no tag + rows           -> refuse: a database from before M3a may hold demo data
        tag != source           -> refuse: live and demo must never share one file
        """
        if source not in KNOWN_SOURCES:
            raise SourceMismatchError(
                f"unknown source {source!r}; expected one of {sorted(KNOWN_SOURCES)}"
            )
        stored = self.get_meta("source")
        if stored is None:
            contracts, quotes = self.row_counts()
            if contracts or quotes:
                raise SourceMismatchError(  # nothing has been created or written
                    f"database {self.engine.url} holds {contracts} contracts and {quotes} quotes "
                    "but has no source tag. Refusing to start: an untagged database may contain "
                    "demo data. Back it up, then either label it "
                    "(python tools/label_db.py --source <source> --force) or move it aside and "
                    "start with an empty database."
                )
            self.create_schema()
            with Session(self.engine) as session, session.begin():
                session.merge(Meta(key="source", value=source))
                session.merge(Meta(key="schema_version", value=str(SCHEMA_VERSION)))
            return
        if stored != source:
            raise SourceMismatchError(
                f"database {self.engine.url} is tagged source={stored!r} but this run is "
                f"source={source!r}. Refusing to start: live and demo data must never share one "
                "database. Point DATABASE_URL at another file (default: "
                "sqlite:///./options_<source>.db) or label the database explicitly with "
                "tools/label_db.py."
            )
        version = self.get_meta("schema_version")
        if version is not None and version != str(SCHEMA_VERSION):
            raise SourceMismatchError(
                f"database {self.engine.url} has schema_version={version!r} but this code expects "
                f"{SCHEMA_VERSION}. Refusing to start: apply the matching migration first."
            )
        self.create_schema()  # accepted: tables added by a later migration may be missing
        if version is None:
            with Session(self.engine) as session, session.begin():
                session.merge(Meta(key="schema_version", value=str(SCHEMA_VERSION)))

    def save_snapshot(self, contracts: list[dict], ts: datetime) -> int:
        """Store the contracts that changed since their last stored row. Returns rows written."""
        ts_utc = ts.astimezone(timezone.utc).replace(tzinfo=None)
        new_contracts: list[Contract] = []
        quotes: list[dict] = []
        pending_state: dict[str, tuple] = {}

        for c in contracts:
            if c["last"] is None and c["bid"] is None and c["ask"] is None:
                continue  # nothing quoted yet
            state = (c["underlying_price"], c["last"], c["bid"], c["ask"], c["volume"], c["open_interest"])
            if self._last_state.get(c["ins_code"]) == state:
                continue
            pending_state[c["ins_code"]] = state
            if c["ins_code"] not in self._known:
                new_contracts.append(
                    Contract(
                        ins_code=c["ins_code"],
                        symbol=c["symbol"],
                        name=c["name"],
                        option_type=c["option_type"],
                        underlying_code=c["underlying_code"],
                        underlying_symbol=c["underlying_symbol"],
                        strike=c["strike"],
                        expiry=c["expiry"],
                        contract_size=c["contract_size"],
                    )
                )
            quotes.append(
                {
                    "ins_code": c["ins_code"],
                    "ts": ts_utc,
                    "underlying_price": c["underlying_price"],
                    "last": c["last"],
                    "bid": c["bid"],
                    "ask": c["ask"],
                    "volume": c["volume"],
                    "open_interest": c["open_interest"],
                    "iv": c["iv"],
                    "delta": c["delta"],
                }
            )

        if not quotes:
            return 0
        with Session(self.engine) as session, session.begin():
            for contract in new_contracts:
                session.merge(contract)
            session.flush()
            session.execute(insert(Quote), quotes)
        # remember only after a successful commit
        self._known.update(c.ins_code for c in new_contracts)
        self._last_state.update(pending_state)
        return len(quotes)

    def history(self, ins_code: str, limit: int = 500) -> list[dict]:
        """Most recent `limit` stored rows of one contract, oldest first."""
        stmt = select(Quote).where(Quote.ins_code == ins_code).order_by(Quote.ts.desc()).limit(limit)
        with Session(self.engine) as session:
            rows = session.execute(stmt).scalars().all()
        return [
            {
                "ts": row.ts.isoformat() + "Z",
                "underlying_price": row.underlying_price,
                "last": row.last,
                "bid": row.bid,
                "ask": row.ask,
                "volume": row.volume,
                "open_interest": row.open_interest,
                "iv": row.iv,
                "delta": row.delta,
            }
            for row in reversed(rows)
        ]
