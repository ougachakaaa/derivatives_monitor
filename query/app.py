"""FastAPI serves JSON only. The independent dashboard owns all frontend assets."""
import os
import re
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from storage import QueryError, Store
from contract_coverage import coverage
from market_calendar import sessions, DEFAULT_DIRECTORY


def create_app(directory=None, calendar_directory=None):
    app = FastAPI(title="Derivatives Monitor read API", version="0.1.0")
    store = Store(directory or os.environ.get("DATA_DIR", "/data"))
    calendar_directory = calendar_directory or os.environ.get("MARKET_CALENDAR_DIR", DEFAULT_DIRECTORY)

    @app.exception_handler(QueryError)
    async def query_error(request, error):
        return JSONResponse({"error": error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"error": "Invalid or missing query parameters"}, status_code=400)

    @app.exception_handler(OSError)
    async def io_error(request, error):
        return JSONResponse({"error": "Shared data cannot be read"}, status_code=503)

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    def parameters(request, allowed):
        keys = [k for k, _ in request.query_params.multi_items()]
        if set(keys) - set(allowed) or len(keys) != len(set(keys)):
            raise QueryError(400, "Unknown or repeated query parameters")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "query"}

    @app.get("/api/health")
    def health():
        try:
            store.check_directory()
            data = {"readable": True}
        except QueryError as error:
            data = {"readable": False, "error": error.message}
        return {"query": {"status": "healthy"}, "data": data, "collector": store.heartbeat()}

    @app.get("/api/sessions")
    def market_sessions(request: Request, exchange: str | None = None,
                        product: str | None = None, at: str | None = None):
        parameters(request, ("exchange", "product", "at"))
        try:
            return sessions(at, exchange, product, calendar_directory)
        except (ValueError, OverflowError):
            raise QueryError(400, "Invalid exchange/product or at (timezone required)") from None

    @app.get("/api/coverage")
    def contract_coverage(request: Request):
        parameters(request, ())
        try:
            return coverage(store, calendar_directory)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise QueryError(503, "Coverage files unavailable or invalid") from None

    @app.get("/api/days")
    def days(request: Request):
        parameters(request, ())
        return {"days": store.days()}

    @app.get("/api/summary")
    def summary(request: Request, day: str):
        parameters(request, ("day",))
        return store.summary(day)

    @app.get("/api/snapshots")
    def snapshots(request: Request, day: str, instrument: str | None = None, limit: int = 50):
        parameters(request, ("day", "instrument", "limit"))
        if not 1 <= limit <= 200 or (instrument is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", instrument)):
            raise QueryError(400, "limit must be 1–200 and instrument must be an exact code")
        return store.snapshots(day, instrument, limit)

    return app


app = create_app()
