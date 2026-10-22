"""
database.py - persistent storage (SQLite by default, PostgreSQL via DATABASE_URL).

contracts  one row per option contract: static facts (strike, expiry, underlying ...)
quotes     time series of prices / open interest / IV. A row is written only when
           something changed since the previous row of that contract, so polling
           after the close does not fill the disk with duplicates.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, create_engine, insert, select
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


class Database:
    def __init__(self, url: str) -> None:
        options: dict = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}  # used from worker threads
            if url in ("sqlite://", "sqlite:///:memory:"):
                options["poolclass"] = StaticPool  # one shared connection for in-memory DBs
        self.engine = create_engine(url, **options)
        Base.metadata.create_all(self.engine)
        self._known: set[str] = set()
        self._last_state: dict[str, tuple] = {}

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
