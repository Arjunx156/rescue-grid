from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.db import engine
from app.core.logging import configure_logging, log
from app.core.redis import redis
from app.core.settings import get_settings
from app.routers import (
    admin,
    analytics,
    auth,
    cases,
    disasters,
    dispatch,
    field,
    intake,
    replay,
    sos,
    teams,
    water,
    webhooks,
    ws,
)
from app.services.geocode import gazetteer


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    if settings.sentry_dsn:
        import sentry_sdk

        # SOS bodies and the locals around them hold phone numbers and health details: never send them
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.env,
            traces_sample_rate=0.05,
            send_default_pii=False,
            include_local_variables=False,
            max_request_body_size="never",
        )
    # load the gazetteer before the first SOS needs it
    await asyncio.to_thread(gazetteer, str(settings.data_dir))
    workers: asyncio.Task[None] | None = None
    if settings.workers_inline:
        from app.workers import run_all

        workers = asyncio.create_task(run_all())
    log.info(
        "api.ready",
        env=settings.env,
        llm=settings.llm_provider,
        router=settings.router,
        whatsapp=settings.whatsapp_enabled,
        inline_workers=settings.workers_inline,
    )
    yield
    if workers:
        workers.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await workers
    await engine().dispose()


app = FastAPI(
    title="Rescue Grid API",
    version="1.0.0",
    description="Turns chaotic flood SOS messages into a live, prioritised rescue plan.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def headers_and_timing(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/v1/") and "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    ms = (time.perf_counter() - started) * 1000
    response.headers["Server-Timing"] = f"app;dur={ms:.1f}"
    if ms > 1500:
        log.warning("http.slow", path=request.url.path, ms=round(ms))
    return response


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("http.error", path=request.url.path, error=str(exc)[:300])
    return JSONResponse({"detail": "Something went wrong on our side. It has been logged."}, status_code=500)


@app.get("/health", tags=["ops"])
async def health() -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        async with engine().connect() as conn:
            await conn.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"down: {e.__class__.__name__}"
    try:
        await redis().ping()
        beat = await redis().get("worker:heartbeat")
        checks["redis"] = "ok"
        checks["workers"] = "ok" if beat and time.time() - float(beat) < 30 else "stale"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"down: {e.__class__.__name__}"
    healthy = checks.get("database") == "ok" and checks.get("redis") == "ok"
    return JSONResponse({"status": "ok" if healthy else "degraded", **checks}, status_code=200 if healthy else 503)


for module in (auth, disasters, cases, sos, intake, teams, dispatch, field, analytics, replay, admin, webhooks, water):
    app.include_router(module.router)
app.include_router(ws.router)
