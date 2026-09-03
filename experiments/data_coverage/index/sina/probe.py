"""Capture raw Sina index snapshot responses for the coverage experiment.

This probe deliberately does not normalize or assign meanings to response fields.
It saves the response bytes as received and records only whether each requested
symbol has a non-empty declaration in the batch response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_TIMEOUT_SECONDS = 15.0
USER_AGENT = "Mozilla/5.0 DerivativesMonitorCoverageProbe/1.0"
DECLARATION_PATTERN = re.compile(
    rb"var\s+hq_str_([A-Za-z0-9_]+)=\"([^\"]*)\";?"
)
CHARSET_PATTERN = re.compile(
    r"(?:^|;)\s*charset\s*=\s*[\"']?([^;\"'\s]+)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class Target:
    name: str
    official_code: str
    candidate: str


TARGETS = (
    Target("上证50", "000016", "sh000016"),
    Target("沪深300", "000300", "sh000300"),
    Target("中证500", "000905", "sh000905"),
    Target("中证1000", "000852", "sh000852"),
    Target("中证2000", "932000", "si932000"),
    Target("科创50", "000688", "sh000688"),
    Target("创业板指", "399006", "sz399006"),
)


@dataclass(frozen=True)
class Attempt:
    label: str
    url: str
    referer: str


def build_attempts() -> tuple[Attempt, ...]:
    symbols = ",".join(target.candidate for target in TARGETS)
    return (
        Attempt(
            label="hq_batch",
            url=f"https://hq.sinajs.cn/list={symbols}",
            referer="https://finance.sina.com.cn/",
        ),
        Attempt(
            label="hq_etag_batch",
            url=f"https://hq.sinajs.cn/etag.php?list={symbols}",
            referer="https://vip.stock.finance.sina.com.cn/",
        ),
    )


def build_market_center_attempt() -> Attempt:
    endpoint = (
        "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        "Market_Center.getHQNodeDataSimple"
    )
    parameters = {
        "page": "1",
        "num": "5000",
        "sort": "symbol",
        "asc": "1",
        "node": "hs_s",
        "_s_r_a": "page",
    }
    return Attempt(
        label="market_center_index_list",
        url=f"{endpoint}?{urlencode(parameters)}",
        referer="https://vip.stock.finance.sina.com.cn/",
    )


def now_shanghai() -> datetime:
    return datetime.now(tz=SHANGHAI)


def json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def inspect_declarations(body: bytes) -> dict[str, int]:
    """Return symbol to payload byte length without interpreting field layout."""

    return {
        match.group(1).decode("ascii"): len(match.group(2))
        for match in DECLARATION_PATTERN.finditer(body)
    }


def declared_charset(headers: dict[str, str]) -> str | None:
    content_type = next(
        (
            value
            for name, value in headers.items()
            if name.lower() == "content-type"
        ),
        None,
    )
    if content_type is None:
        return None
    match = CHARSET_PATTERN.search(content_type)
    return match.group(1) if match else None


def write_utf8_companion(
    body_path: Path,
    body: bytes,
    headers: dict[str, str],
) -> dict[str, Any]:
    """Write a readable UTF-8 copy while preserving source bytes in body_path."""

    charset = declared_charset(headers)
    result: dict[str, Any] = {
        "declared_charset": charset,
        "raw_is_utf8": True,
        "utf8_companion": None,
        "error": None,
    }
    try:
        body.decode("utf-8")
        return result
    except UnicodeDecodeError:
        result["raw_is_utf8"] = False

    if charset is None:
        result["error"] = (
            "Raw body is not UTF-8 and the response did not declare a charset."
        )
        return result

    try:
        text = body.decode(charset, errors="strict")
    except (LookupError, UnicodeDecodeError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
        return result

    companion_path = body_path.with_suffix(".utf8.txt")
    companion = text.encode("utf-8")
    companion_path.write_bytes(companion)
    result["utf8_companion"] = {
        "file": companion_path.name,
        "bytes": len(companion),
        "sha256": hashlib.sha256(companion).hexdigest(),
    }
    return result


def capture_attempt(
    attempt: Attempt,
    attempt_number: int,
    run_directory: Path,
    timeout_seconds: float,
) -> tuple[dict[str, Any], bytes]:
    prefix = f"{attempt_number:02d}_{attempt.label}"
    body_path = run_directory / f"{prefix}.body"
    record_path = run_directory / f"{prefix}.json"
    request_headers = {
        "Referer": attempt.referer,
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
    }
    request = Request(attempt.url, headers=request_headers, method="GET")
    started = time.monotonic()
    received_at: str | None = None
    body = b""

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            received_at = now_shanghai().isoformat(timespec="milliseconds")
            record: dict[str, Any] = {
                "label": attempt.label,
                "request": {
                    "method": "GET",
                    "url": attempt.url,
                    "headers": request_headers,
                    "timeout_seconds": timeout_seconds,
                },
                "response": {
                    "received_at": received_at,
                    "status": response.status,
                    "reason": response.reason,
                    "headers": dict(response.headers.items()),
                    "body_file": body_path.name,
                    "body_bytes": len(body),
                    "body_sha256": hashlib.sha256(body).hexdigest(),
                },
                "error": None,
            }
    except HTTPError as error:
        body = error.read()
        received_at = now_shanghai().isoformat(timespec="milliseconds")
        record = {
            "label": attempt.label,
            "request": {
                "method": "GET",
                "url": attempt.url,
                "headers": request_headers,
                "timeout_seconds": timeout_seconds,
            },
            "response": {
                "received_at": received_at,
                "status": error.code,
                "reason": error.reason,
                "headers": dict(error.headers.items()) if error.headers else {},
                "body_file": body_path.name,
                "body_bytes": len(body),
                "body_sha256": hashlib.sha256(body).hexdigest(),
            },
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
    except (TimeoutError, URLError, OSError) as error:
        received_at = now_shanghai().isoformat(timespec="milliseconds")
        record = {
            "label": attempt.label,
            "request": {
                "method": "GET",
                "url": attempt.url,
                "headers": request_headers,
                "timeout_seconds": timeout_seconds,
            },
            "response": None,
            "error": {
                "received_at": received_at,
                "type": type(error).__name__,
                "message": str(error),
            },
        }

    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if body or record.get("response") is not None:
        body_path.write_bytes(body)
        response_record = record["response"]
        response_record["text_decoding"] = write_utf8_companion(
            body_path=body_path,
            body=body,
            headers=response_record["headers"],
        )
    json_dump(record_path, record)
    return record, body


def target_observations(
    attempts: list[tuple[dict[str, Any], dict[str, int]]],
) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for target in TARGETS:
        evidence = []
        for record, declarations in attempts:
            if target.candidate in declarations:
                payload_bytes = declarations[target.candidate]
                evidence.append(
                    {
                        "attempt": record["label"],
                        "declaration_present": True,
                        "payload_nonempty": payload_bytes > 0,
                        "payload_bytes": payload_bytes,
                    }
                )
        observations.append(
            {
                "name": target.name,
                "official_code": target.official_code,
                "candidate": target.candidate,
                "evidence": evidence,
                "nonempty_declaration_observed": any(
                    item["payload_nonempty"] for item in evidence
                ),
            }
        )
    return observations


def discovery_observations(body: bytes) -> list[dict[str, Any]]:
    """Record byte-level search signals without assuming a response schema."""

    observations = []
    for target in TARGETS:
        observations.append(
            {
                "name": target.name,
                "official_code": target.official_code,
                "candidate": target.candidate,
                "official_code_bytes_present": target.official_code.encode("ascii")
                in body,
                "candidate_bytes_present": target.candidate.encode("ascii") in body,
                "name_gb18030_bytes_present": target.name.encode("gb18030") in body,
                "name_utf8_bytes_present": target.name.encode("utf-8") in body,
            }
        )
    return observations


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture raw Sina responses for the Index coverage experiment."
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).with_name("samples"),
        help="Directory under which a timestamped run directory is created.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Per-request timeout in seconds (default: 15).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")

    started_at = now_shanghai()
    run_id = started_at.strftime("%Y%m%dT%H%M%S%z")
    run_directory = args.output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=False)

    inspected_attempts: list[tuple[dict[str, Any], dict[str, int]]] = []
    for attempt_number, attempt in enumerate(build_attempts(), start=1):
        record, body = capture_attempt(
            attempt=attempt,
            attempt_number=attempt_number,
            run_directory=run_directory,
            timeout_seconds=args.timeout,
        )
        declarations = inspect_declarations(body)
        inspected_attempts.append((record, declarations))
        if all(
            declarations.get(target.candidate, 0) > 0 for target in TARGETS
        ):
            break

    observations = target_observations(inspected_attempts)
    discovery_record: dict[str, Any] | None = None
    discovery_signals: list[dict[str, Any]] = []
    if not all(
        observation["nonempty_declaration_observed"]
        for observation in observations
    ):
        discovery_record, discovery_body = capture_attempt(
            attempt=build_market_center_attempt(),
            attempt_number=len(inspected_attempts) + 1,
            run_directory=run_directory,
            timeout_seconds=args.timeout,
        )
        discovery_signals = discovery_observations(discovery_body)

    completed_at = now_shanghai()
    summary = {
        "experiment": "Index × Sina snapshot coverage",
        "run_id": run_id,
        "started_at": started_at.isoformat(timespec="milliseconds"),
        "completed_at": completed_at.isoformat(timespec="milliseconds"),
        "run_directory": run_directory.name,
        "attempts": [record["label"] for record, _ in inspected_attempts],
        "targets": observations,
        "fallback_discovery": {
            "attempt": discovery_record["label"] if discovery_record else None,
            "signals": discovery_signals,
            "note": (
                "Byte-presence signals only. They do not assert a response schema "
                "or prove that a matching entry contains usable snapshot data."
            ),
        },
        "note": (
            "Derived inventory only. It records declaration presence and payload "
            "length without assigning meanings to response fields."
        ),
    }
    json_dump(run_directory / "observations.json", summary)

    complete = all(
        observation["nonempty_declaration_observed"]
        for observation in observations
    )
    print(run_directory)
    print(
        f"non-empty declarations: "
        f"{sum(item['nonempty_declaration_observed'] for item in observations)}"
        f"/{len(observations)}"
    )
    return 0 if complete else 1


if __name__ == "__main__":
    sys.exit(main())
