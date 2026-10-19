"""
main.py - FastAPI application.

REST
    GET  /api/health                              collector / cache status
    GET  /api/underlyings                         underlyings that have options, with their expiries
    GET  /api/option-chain?underlying=&expiry=    call / put ladder of one expiry (nearest if omitted)
    POST /api/payoff                              expiry profit / loss curve of a strategy
    GET  /api/contracts/{ins_code}/history        stored price / IV history of one contract
WebSocket
    /ws/option-chain/{underlying}?expiry=         pushes the ladder after every poll

Run:   uvicorn main:app --reload      (interactive docs: http://127.0.0.1:8000/docs)
Demo:  OPTIONS_SOURCE=demo uvicorn main:app    (synthetic data, no TSETMC needed)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager, contextmanager
from dataclasses import asdict

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from cache import create_cache
from calculator import Leg, strategy_payoff
from config import Settings
from config import settings as default_settings
from database import Database
from demo_collector import DemoCollector
from schemas import ChainResponse, PayoffRequest, PayoffResponse, UnderlyingMeta
from service import MarketService, NoDataError, NotFoundError, chain_key
from tsetmc_collector import TSETMCCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@contextmanager
def _http_errors():
    """Translate service-level errors into proper HTTP status codes."""
    try:
        yield
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NoDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def create_app(settings: Settings | None = None, collector=None) -> FastAPI:
    """App factory: tests inject their own settings and collector."""
    cfg = settings or default_settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cache = await create_cache(cfg.redis_url)
        db = Database(cfg.database_url)
        source = collector or (DemoCollector(cfg) if cfg.source == "demo" else TSETMCCollector(cfg))
        service = MarketService(cfg, source, cache, db)
        app.state.service = service
        service.start()
        try:
            yield
        finally:
            await service.stop()

    app = FastAPI(title="Option Platform API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cfg.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def service_of(request: Request) -> MarketService:
        return request.app.state.service

    # -- REST ---------------------------------------------------------------------
    @app.get("/api/health")
    async def health(request: Request) -> dict:
        return service_of(request).status()

    @app.get("/api/underlyings", response_model=list[UnderlyingMeta])
    async def underlyings(request: Request):
        with _http_errors():
            return await service_of(request).get_underlyings()

    @app.get("/api/option-chain", response_model=ChainResponse)
    async def option_chain(
        request: Request,
        underlying: str = Query(..., description="Underlying instrument code or symbol"),
        expiry: str | None = Query(None, description="Expiry as YYYY-MM-DD; nearest if omitted"),
    ):
        with _http_errors():
            return await service_of(request).get_chain(underlying, expiry)

    @app.post("/api/payoff", response_model=PayoffResponse)
    async def payoff(body: PayoffRequest):
        legs = [Leg(**leg.model_dump()) for leg in body.legs]
        try:
            result = strategy_payoff(
                legs, spot=body.spot, x_min=body.x_min, x_max=body.x_max, points=body.points
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return asdict(result)

    @app.get("/api/contracts/{ins_code}/history")
    async def contract_history(request: Request, ins_code: str, limit: int = Query(500, ge=1, le=5000)):
        return await service_of(request).history(ins_code, limit)

    # -- WebSocket ----------------------------------------------------------------
    @app.websocket("/ws/option-chain/{underlying}")
    async def option_chain_stream(websocket: WebSocket, underlying: str, expiry: str | None = None):
        service: MarketService = websocket.app.state.service
        try:
            key = await service.resolve(underlying, expiry)
        except (NoDataError, NotFoundError) as exc:
            await websocket.accept()
            await websocket.close(code=4404 if isinstance(exc, NotFoundError) else 1013)
            return

        await service.hub.connect(key, websocket)
        try:
            first = await service.cache.get_json(chain_key(*key))  # do not make the client wait for the next poll
            if first is not None:
                await websocket.send_json(first)
            while True:
                await websocket.receive_text()  # the server only pushes; this just notices disconnects
        except WebSocketDisconnect:
            pass
        finally:
            service.hub.disconnect(key, websocket)

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
