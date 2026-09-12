"""FastAPI serves JSON only. The independent dashboard owns all frontend assets."""
import json
import os
import re
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from storage import QueryError, Store
from contract_coverage import coverage
from indicator_service import IndicatorRequestError, skew_indicator_service
from market_calendar import sessions, DEFAULT_DIRECTORY
from skew_references import ReferenceRepository
from skew_service import SkewService


def create_app(directory=None, calendar_directory=None, *, reference_directory=None,
               target_month=None, reference_repository=None, indicator_service=None):
    app = FastAPI(title="Derivatives Monitor read API", version="0.1.0")
    store = Store(directory or os.environ.get("DATA_DIR", "/data"))
    calendar_directory = calendar_directory or os.environ.get("MARKET_CALENDAR_DIR", DEFAULT_DIRECTORY)
    skew = SkewService(store, reference_repository or ReferenceRepository(
        reference_directory or os.environ.get("SKEW_REFERENCE_DIR", store.directory / 'references/analytics')),
        calendar_directory, target_month or os.environ.get("SKEW_TARGET_MONTH"))
    indicators = indicator_service if indicator_service is not None else skew_indicator_service(skew)

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

    @app.get("/api/skew/latest")
    def skew_latest(request: Request, month: str | None = None, at: str | None = None,
                    raw_revision: int | None = None, bundle_id: str | None = None):
        parameters(request, ("month", "at", "raw_revision", "bundle_id"))
        return skew.query('latest', month=month, at=at, raw_revision=raw_revision, bundle_id=bundle_id)

    @app.get("/api/skew/minute")
    def skew_minute(request: Request, day: str, minute: str, month: str | None = None,
                    at: str | None = None, raw_revision: int | None = None,
                    bundle_id: str | None = None):
        parameters(request, ("day", "minute", "month", "at", "raw_revision", "bundle_id"))
        return skew.query('minute', day=day, minute=minute, month=month, at=at,
                          raw_revision=raw_revision, bundle_id=bundle_id)

    @app.get("/api/skew/series")
    def skew_series(request: Request, day: str, month: str | None = None,
                    at: str | None = None, raw_revision: int | None = None,
                    bundle_id: str | None = None):
        parameters(request, ("day", "month", "at", "raw_revision", "bundle_id"))
        return skew.query('series', day=day, month=month, at=at,
                          raw_revision=raw_revision, bundle_id=bundle_id)

    @app.post("/api/indicators/evaluate")
    async def indicator_evaluate(request: Request):
        parameters(request, ())
        if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() != 'application/json':
            raise QueryError(400, 'Indicator request body must be JSON')
        try:
            def strict_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('duplicate JSON field')
                    result[key] = value
                return result

            def reject_constant(value):
                raise ValueError('non-finite JSON number: ' + value)

            body = json.loads(await request.body(), object_pairs_hook=strict_object,
                              parse_constant=reject_constant)
        except (ValueError, UnicodeDecodeError):
            raise QueryError(400, 'Invalid Indicator request JSON') from None
        try:
            return indicators.evaluate(body)
        except IndicatorRequestError as error:
            raise QueryError(400, str(error)) from None

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
