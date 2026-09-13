FROM scratch AS context-audit
COPY . /

FROM python:3.12-slim-bookworm AS build
ENV POETRY_VIRTUALENVS_IN_PROJECT=true PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN pip install --no-cache-dir poetry==2.2.1
COPY query/pyproject.toml query/poetry.lock ./
RUN poetry sync --no-interaction
COPY query/__init__.py query/app.py query/storage.py query/contract_coverage.py query/market_calendar.py query/market_frame.py query/analytics.py query/skew_service.py query/skew_references.py query/indicator_service.py ./query/
COPY query/calendars/ ./query/calendars/
COPY query/tests/ ./query/tests/
RUN poetry run python -m unittest discover -s query/tests -t . -v && poetry sync --only main --no-interaction

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY query/__init__.py query/app.py query/storage.py query/contract_coverage.py query/market_calendar.py query/market_frame.py query/analytics.py query/skew_service.py query/skew_references.py query/indicator_service.py ./query/
COPY query/calendars/ ./query/calendars/
USER 65532:65532
EXPOSE 8000
STOPSIGNAL SIGTERM
CMD ["uvicorn", "query.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
