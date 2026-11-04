"""Event, cursor, receipt, and enriched-journal persistence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from .models import ArchivalReceipt, CursorState


class EventReader:
    """Read the provider-neutral JSONL protocol emitted by AID2E."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def read_after(self, cursor: int = 0, limit: int = 1000) -> list[dict[str, Any]]:
        if cursor < 0:
            raise ValueError("cursor must be non-negative")
        if limit < 1:
            raise ValueError("limit must be positive")
        events = []
        for event in self.iter_events():
            if int(event["sequence"]) > cursor:
                events.append(event)
            if len(events) >= limit:
                break
        return events

    def iter_events(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        expected_run_id = None
        previous_sequence = 0
        with self.path.open("r", encoding="utf-8") as stream:
            while True:
                line = stream.readline()
                if not line:
                    break
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    if not line.endswith("\n"):
                        break
                    raise RuntimeError(f"Invalid event JSON in {self.path}") from exc
                _validate_event(event)
                sequence = int(event["sequence"])
                if sequence <= previous_sequence:
                    raise RuntimeError(
                        f"Non-monotonic sequence {sequence} in {self.path}"
                    )
                if previous_sequence and sequence != previous_sequence + 1:
                    raise RuntimeError(
                        f"Event sequence gap after {previous_sequence} in {self.path}"
                    )
                run_id = str(event["run_id"])
                expected_run_id = expected_run_id or run_id
                if run_id != expected_run_id:
                    raise RuntimeError(f"Mixed run IDs in {self.path}")
                previous_sequence = sequence
                yield event


class CursorStore:
    """Atomically persist observation and archival progress."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()

    def load(self) -> CursorState:
        if not self.path.exists():
            return CursorState()
        return CursorState.from_dict(
            json.loads(self.path.read_text(encoding="utf-8"))
        )

    def save(self, state: CursorState) -> None:
        _atomic_json_write(self.path, state.to_dict())


class ReceiptJournal:
    """Append-only OpenViking receipts owned by the agentic layer."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, receipt: ArchivalReceipt) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt.to_dict(), sort_keys=True))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def all(self) -> list[ArchivalReceipt]:
        if not self.path.exists():
            return []
        receipts = []
        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    receipts.append(ArchivalReceipt.from_dict(json.loads(line)))
                except Exception as exc:
                    raise RuntimeError(
                        f"Invalid receipt at {self.path}:{line_number}"
                    ) from exc
        return receipts

    def latest(self) -> dict[tuple[str, str, str], ArchivalReceipt]:
        latest = {}
        for receipt in self.all():
            key = (
                receipt.source_event_id,
                receipt.artifact_id,
                receipt.sanitized_sha256,
            )
            latest[key] = receipt
        return latest

    def latest_for_event(self, event_id: str) -> list[ArchivalReceipt]:
        latest = self.latest().values()
        return [item for item in latest if item.source_event_id == event_id]


def materialize_enriched_journal(
    event_path: str | Path,
    receipt_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Join immutable framework events with latest OpenViking receipts."""

    receipts = ReceiptJournal(receipt_path).latest().values()
    by_event: dict[str, list[ArchivalReceipt]] = {}
    for receipt in receipts:
        if receipt.source_event_id.startswith("__"):
            continue
        by_event.setdefault(receipt.source_event_id, []).append(receipt)

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for event in EventReader(event_path).iter_events():
                event_receipts = sorted(
                    by_event.get(str(event["event_id"]), []),
                    key=lambda item: item.artifact_id,
                )
                statuses = {item.status for item in event_receipts}
                evidence_count = len(event.get("evidence") or [])
                if not evidence_count:
                    status = "not_required"
                elif event_receipts and statuses == {"verified"}:
                    status = "verified"
                elif statuses & {"accepted", "verified"}:
                    status = "accepted"
                elif "failed" in statuses:
                    status = "failed"
                else:
                    status = "pending"
                enriched = dict(event)
                enriched["openviking"] = {
                    "status": status,
                    "records": [
                        {
                            "artifact_id": item.artifact_id,
                            "kind": item.kind,
                            "uri": item.openviking_uri,
                            "ingestion_task_id": item.ingestion_task_id,
                            "sha256": item.sanitized_sha256,
                            "status": item.status,
                        }
                        for item in event_receipts
                    ],
                }
                stream.write(json.dumps(enriched, sort_keys=True))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return output


def _validate_event(event: Any) -> None:
    if not isinstance(event, dict):
        raise RuntimeError("Event must be a JSON object")
    required = {"schema_version", "event_id", "sequence", "event_type", "run_id"}
    missing = required - event.keys()
    if missing:
        raise RuntimeError(f"Event is missing fields: {sorted(missing)}")
    if int(event["schema_version"]) != 1:
        raise RuntimeError(
            f"Unsupported event schema version: {event['schema_version']}"
        )


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
