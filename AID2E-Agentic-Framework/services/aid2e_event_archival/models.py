"""Data contracts owned by the external AID2E evidence archiver."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PreparedEvidence:
    artifact_id: str
    kind: str
    source_path: Path
    prepared_path: Path
    source_sha256: str
    sanitized_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ArchivalReceipt:
    run_id: str
    source_event_id: str
    source_sequence: int
    artifact_id: str
    kind: str
    source_sha256: str
    sanitized_sha256: str
    status: str
    openviking_uri: str | None = None
    ingestion_task_id: str | None = None
    attempt: int = 1
    archived_at: str = ""
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["archived_at"] = self.archived_at or utc_now()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ArchivalReceipt":
        return cls(**payload)


@dataclass
class CursorState:
    run_id: str | None = None
    last_observed_sequence: int = 0
    last_archived_sequence: int = 0
    last_verified_sequence: int = 0
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["updated_at"] = utc_now()
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CursorState":
        return cls(**payload)
