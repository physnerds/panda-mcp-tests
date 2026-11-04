"""Securely resolve and sanitize evidence referenced by AID2E events."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .models import PreparedEvidence


MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
TEXT_SUFFIXES = {".json", ".jsonl", ".log", ".md", ".txt", ".yaml", ".yml"}

_REDACTIONS = (
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)((?:api[_-]?key|token|password)\s*[=:]\s*)[^\s,;]+"), r"\1<REDACTED>"),
    (
        re.compile(
            r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "<REDACTED_PRIVATE_KEY>",
    ),
    (re.compile(r"/home/[^/\s]+"), "<HOME>"),
)


def prepare_evidence(
    *,
    run_dir: str | Path,
    state_dir: str | Path,
    event: dict[str, Any],
    evidence: dict[str, Any],
    max_bytes: int = MAX_EVIDENCE_BYTES,
) -> PreparedEvidence:
    """Resolve, validate, hash, and sanitize one referenced artifact."""

    root = Path(run_dir).expanduser().resolve()
    relative = Path(str(evidence["relative_path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe evidence path: {relative}")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise FileNotFoundError(f"Evidence file is unavailable: {relative}")
    source = candidate.resolve()
    try:
        source.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Evidence escapes run directory: {relative}") from exc

    before = source.stat()
    expected_size = evidence.get("size_bytes")
    if expected_size is not None and int(expected_size) != before.st_size:
        raise RuntimeError(
            f"Evidence size no longer matches its event: {relative} "
            f"(expected {expected_size}, found {before.st_size})"
        )
    if before.st_size > max_bytes:
        raise ValueError(
            f"Evidence exceeds {max_bytes} bytes: {relative} ({before.st_size})"
        )
    source_bytes = source.read_bytes()
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Evidence changed while being read: {relative}")

    if source.suffix.lower() not in TEXT_SUFFIXES:
        raise ValueError(f"Unsupported evidence type: {source.suffix or '<none>'}")
    text = source_bytes.decode("utf-8", errors="replace")
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    sanitized_bytes = text.encode("utf-8")

    artifact_id = str(evidence["artifact_id"])
    output_dir = (
        Path(state_dir).expanduser().resolve()
        / "sanitized"
        / _safe_component(str(event["run_id"]))
        / f"event-{int(event['sequence']):08d}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{_safe_component(artifact_id)}{source.suffix.lower()}"
    _atomic_bytes_write(output_path, sanitized_bytes)

    return PreparedEvidence(
        artifact_id=artifact_id,
        kind=str(evidence.get("kind", "unknown")),
        source_path=source,
        prepared_path=output_path,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        sanitized_sha256=hashlib.sha256(sanitized_bytes).hexdigest(),
        size_bytes=len(sanitized_bytes),
    )


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not cleaned:
        raise ValueError(f"Value cannot form a safe path component: {value!r}")
    return cleaned


def _atomic_bytes_write(path: Path, payload: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
