FROM scratch AS context-audit
COPY . /

FROM python:3.12-slim-bookworm AS build
ENV POETRY_VIRTUALENVS_IN_PROJECT=true PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN pip install --no-cache-dir poetry==2.2.1
COPY query/pyproject.toml query/poetry.lock ./
RUN poetry sync --no-interaction
COPY query/__init__.py query/app.py query/errors.py query/indicator_service.py ./query/
COPY data_provider/__init__.py data_provider/errors.py data_provider/storage.py data_provider/contract_coverage.py data_provider/market_calendar.py data_provider/market_frame.py ./data_provider/
COPY data_provider/calendars/ ./data_provider/calendars/
COPY data_provider/tests/ ./data_provider/tests/
COPY analytics/__init__.py analytics/errors.py analytics/skew.py analytics/skew_service.py analytics/skew_references.py ./analytics/
COPY analytics/contracts/ ./analytics/contracts/
COPY analytics/tests/ ./analytics/tests/
COPY query/tests/ ./query/tests/
RUN poetry run python -m unittest discover -s data_provider/tests -t . -v \
 && poetry run python -m unittest discover -s analytics/tests -t . -v \
 && poetry run python -m unittest discover -s query/tests -t . -v \
 && poetry sync --only main --no-interaction

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY query/__init__.py query/app.py query/errors.py query/indicator_service.py ./query/
COPY data_provider/__init__.py data_provider/errors.py data_provider/storage.py data_provider/contract_coverage.py data_provider/market_calendar.py data_provider/market_frame.py ./data_provider/
COPY data_provider/calendars/ ./data_provider/calendars/
COPY analytics/__init__.py analytics/errors.py analytics/skew.py analytics/skew_service.py analytics/skew_references.py ./analytics/
USER 65532:65532
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["uvicorn", "query.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
