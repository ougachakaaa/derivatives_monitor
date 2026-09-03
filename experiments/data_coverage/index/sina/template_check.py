"""Inspect local probe samples and compare them with the current template.

The fingerprint deliberately excludes quote values and timestamps. It captures
only response framing, logical field shapes, and the target identifier mapping.
This module never performs network requests or writes template versions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parent
DEFAULT_SAMPLES_ROOT = DEFAULT_ROOT / "samples"
DEFAULT_TEMPLATES_ROOT = DEFAULT_ROOT / "templates"
DECLARATION_PATTERN = re.compile(
    r'var\s+hq_str_([A-Za-z0-9_]+)="([^"]*)";?'
)
CHARSET_PATTERN = re.compile(
    r'(?:^|;)\s*charset\s*=\s*["\']?([^;"\'\s]+)',
    flags=re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
TIME_PATTERN = re.compile(r"\d{2}:\d{2}:\d{2}\Z")
NUMBER_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")


class NoSampleError(RuntimeError):
    pass


class NoTemplateError(RuntimeError):
    pass


def json_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def successful_run(run_directory: Path) -> bool:
    observations_path = run_directory / "observations.json"
    if not observations_path.is_file():
        return False
    observations = read_json(observations_path)
    targets = observations.get("targets")
    return bool(targets) and all(
        target.get("nonempty_declaration_observed") is True
        for target in targets
    )


def select_run(samples_root: Path, run_id: str | None) -> Path:
    if run_id is not None:
        run_directory = samples_root / run_id
        if not run_directory.is_dir() or not successful_run(run_directory):
            raise NoSampleError(
                f"Run {run_id!r} is missing or is not a successful complete run."
            )
        return run_directory

    candidates = sorted(
        (
            path
            for path in samples_root.iterdir()
            if path.is_dir() and successful_run(path)
        ),
        key=lambda path: path.name,
        reverse=True,
    ) if samples_root.is_dir() else []
    if not candidates:
        raise NoSampleError("No successful local sample run is available.")
    return candidates[0]


def quote_record(run_directory: Path) -> tuple[Path, dict[str, Any]]:
    for path in sorted(run_directory.glob("*.json")):
        if path.name == "observations.json":
            continue
        record = read_json(path)
        response = record.get("response")
        if (
            record.get("label") == "hq_batch"
            and isinstance(response, dict)
            and response.get("status") == 200
        ):
            return path, record
    raise NoSampleError(f"No successful hq_batch response in {run_directory}")


def response_charset(response: dict[str, Any]) -> str:
    text_decoding = response.get("text_decoding")
    if isinstance(text_decoding, dict) and text_decoding.get("declared_charset"):
        return str(text_decoding["declared_charset"])

    headers = response.get("headers", {})
    content_type = next(
        (
            str(value)
            for name, value in headers.items()
            if str(name).lower() == "content-type"
        ),
        "",
    )
    match = CHARSET_PATTERN.search(content_type)
    if match is None:
        raise NoSampleError("The hq_batch response does not declare a charset.")
    return match.group(1)


def token_class(value: str) -> str:
    if value == "":
        return "empty"
    if DATE_PATTERN.fullmatch(value):
        return "date"
    if TIME_PATTERN.fullmatch(value):
        return "time"
    if NUMBER_PATTERN.fullmatch(value):
        return "number"
    return "text"


def inspect_run(run_directory: Path) -> dict[str, Any]:
    observations = read_json(run_directory / "observations.json")
    record_path, record = quote_record(run_directory)
    response = record["response"]
    body_path = run_directory / response["body_file"]
    body = body_path.read_bytes()
    body_hash = hashlib.sha256(body).hexdigest()
    if body_hash != response["body_sha256"] or len(body) != response["body_bytes"]:
        raise NoSampleError(f"Raw body metadata mismatch: {body_path}")

    charset = response_charset(response)
    text = body.decode(charset, errors="strict")
    declarations = DECLARATION_PATTERN.findall(text)
    targets = observations["targets"]
    if len(declarations) != len(targets):
        raise NoSampleError(
            "Declaration count does not match the successful target inventory."
        )

    shape_variants: dict[str, dict[str, Any]] = {}
    for _, payload in declarations:
        fields = payload.split(",")
        trailing_delimiter = fields[-1] == ""
        logical_fields = fields[:-1] if trailing_delimiter else fields
        shape = {
            "logical_field_count": len(logical_fields),
            "position_types": [token_class(value) for value in logical_fields],
            "trailing_delimiter": trailing_delimiter,
        }
        shape_variants[json_hash(shape)] = shape

    headers = response.get("headers", {})
    content_type = next(
        (
            str(value).split(";", maxsplit=1)[0].strip().lower()
            for name, value in headers.items()
            if str(name).lower() == "content-type"
        ),
        None,
    )
    format_details = {
        "response_media_type": content_type,
        "declared_charset": charset.lower(),
        "record_wrapper": 'var hq_str_<identifier>="<payload>";',
        "payload_delimiter": ",",
        "record_shape_variants": sorted(
            shape_variants.values(),
            key=lambda shape: json.dumps(shape, sort_keys=True),
        ),
    }
    semantic_details = {
        "targets": sorted(
            (
                {
                    "name": payload.split(",", maxsplit=1)[0],
                    "official_code": target["official_code"],
                    "source_identifier": identifier,
                }
                for target, (identifier, payload) in zip(
                    targets,
                    declarations,
                    strict=True,
                )
            ),
            key=lambda target: target["official_code"],
        )
    }
    return {
        "run_id": run_directory.name,
        "source_sample": {
            "record_file": record_path.name,
            "body_file": body_path.name,
            "body_bytes": len(body),
            "body_sha256": body_hash,
            "received_at": response.get("received_at"),
        },
        "format_fingerprint": {
            "sha256": json_hash(format_details),
            "details": format_details,
        },
        "semantic_fingerprint": {
            "sha256": json_hash(semantic_details),
            "details": semantic_details,
        },
    }


def current_manifest(templates_root: Path) -> tuple[str, dict[str, Any]]:
    current_path = templates_root / "CURRENT"
    if not current_path.is_file():
        raise NoTemplateError("No templates/CURRENT file is available.")
    version = current_path.read_text(encoding="utf-8").strip()
    manifest_path = templates_root / version / "manifest.json"
    if not version or not manifest_path.is_file():
        raise NoTemplateError("The current template manifest is missing.")
    manifest = read_json(manifest_path)
    if manifest.get("version") != version:
        raise NoTemplateError("CURRENT and manifest version do not agree.")
    return version, manifest


def print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect local Sina samples and validate the current template."
    )
    parser.add_argument("command", choices=("inspect", "check"))
    parser.add_argument("--run", help="Specific successful run ID to inspect.")
    parser.add_argument(
        "--samples-root",
        type=Path,
        default=DEFAULT_SAMPLES_ROOT,
        help="Local samples directory.",
    )
    parser.add_argument(
        "--templates-root",
        type=Path,
        default=DEFAULT_TEMPLATES_ROOT,
        help="Versioned templates directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run_directory = select_run(args.samples_root, args.run)
        inspection = inspect_run(run_directory)
        if args.command == "inspect":
            print_json({"status": "INSPECTED", **inspection})
            return 0

        version, manifest = current_manifest(args.templates_root)
        format_match = (
            inspection["format_fingerprint"]["sha256"]
            == manifest["format_fingerprint"]["sha256"]
        )
        semantic_match = (
            inspection["semantic_fingerprint"]["sha256"]
            == manifest["semantic_fingerprint"]["sha256"]
        )
        status = "MATCH" if format_match and semantic_match else "MISMATCH"
        print_json(
            {
                "status": status,
                "template_version": version,
                "format_match": format_match,
                "semantic_match": semantic_match,
                **inspection,
            }
        )
        return 0 if status == "MATCH" else 1
    except NoSampleError as error:
        print_json({"status": "NO_SAMPLE", "message": str(error)})
        return 2
    except NoTemplateError as error:
        print_json({"status": "NO_TEMPLATE", "message": str(error)})
        return 3


if __name__ == "__main__":
    sys.exit(main())
