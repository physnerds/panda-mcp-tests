"""OpenViking archival orchestration for AID2E event evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Protocol

from .evidence import prepare_evidence
from .journal import (
    CursorStore,
    EventReader,
    ReceiptJournal,
    materialize_enriched_journal,
)
from .models import ArchivalReceipt, CursorState, PreparedEvidence, utc_now


TERMINAL_RUN_EVENTS = {
    "run.completed",
    "run.completed_with_failures",
    "run.failed",
    "run.cancelled",
}


class OpenVikingClient(Protocol):
    def add_resource(
        self,
        path: str,
        to: str | None = None,
        parent: str | None = None,
        wait: bool = False,
        timeout: float | None = None,
    ) -> Any: ...

    def read(self, uri: str, offset: int = 0, limit: int = -1) -> Any: ...

    def ls(
        self,
        uri: str,
        simple: bool = False,
        recursive: bool = False,
    ) -> Any: ...


class OpenVikingArchiver:
    """Idempotently upload prepared evidence and persist receipts."""

    def __init__(
        self,
        client: OpenVikingClient,
        receipts: ReceiptJournal,
        *,
        base_uri: str = "viking://resources/evidence/aid2e",
        verify_after_upload: bool = True,
    ) -> None:
        self.client = client
        self.receipts = receipts
        self.base_uri = base_uri.rstrip("/")
        self.verify_after_upload = verify_after_upload

    def archive(
        self,
        event: dict[str, Any],
        prepared: PreparedEvidence,
    ) -> ArchivalReceipt:
        key = (
            str(event["event_id"]),
            prepared.artifact_id,
            prepared.sanitized_sha256,
        )
        previous = self.receipts.latest().get(key)
        if previous and previous.status == "verified":
            return previous
        if previous and previous.status == "accepted" and previous.openviking_uri:
            reconciled = self._try_reconcile(previous)
            return reconciled or previous

        target_uri = self._target_uri(
            str(event["run_id"]),
            int(event["sequence"]),
            prepared.artifact_id,
            prepared.prepared_path.suffix,
        )
        attempt = (previous.attempt + 1) if previous else 1
        try:
            response = self.client.add_resource(
                str(prepared.prepared_path),
                to=target_uri,
                wait=False,
            )
            _raise_for_error_envelope(response)
            uri = _find_uri(response) or target_uri
            receipt = ArchivalReceipt(
                run_id=str(event["run_id"]),
                source_event_id=str(event["event_id"]),
                source_sequence=int(event["sequence"]),
                artifact_id=prepared.artifact_id,
                kind=prepared.kind,
                source_sha256=prepared.source_sha256,
                sanitized_sha256=prepared.sanitized_sha256,
                status="accepted",
                openviking_uri=uri,
                ingestion_task_id=_find_identifier(response),
                attempt=attempt,
                archived_at=utc_now(),
            )
            self.receipts.append(receipt)
            if self.verify_after_upload:
                return self._try_reconcile(receipt) or receipt
            return receipt
        except Exception as exc:
            receipt = ArchivalReceipt(
                run_id=str(event["run_id"]),
                source_event_id=str(event["event_id"]),
                source_sequence=int(event["sequence"]),
                artifact_id=prepared.artifact_id,
                kind=prepared.kind,
                source_sha256=prepared.source_sha256,
                sanitized_sha256=prepared.sanitized_sha256,
                status="failed",
                openviking_uri=target_uri,
                attempt=attempt,
                archived_at=utc_now(),
                error={"type": exc.__class__.__name__, "message": str(exc)},
            )
            self.receipts.append(receipt)
            return receipt

    def archive_file(
        self,
        *,
        run_id: str,
        source_event_id: str,
        source_sequence: int,
        artifact_id: str,
        kind: str,
        path: str | Path,
    ) -> ArchivalReceipt:
        file_path = Path(path).expanduser().resolve()
        content = file_path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        prepared = PreparedEvidence(
            artifact_id=artifact_id,
            kind=kind,
            source_path=file_path,
            prepared_path=file_path,
            source_sha256=digest,
            sanitized_sha256=digest,
            size_bytes=len(content),
        )
        event = {
            "run_id": run_id,
            "event_id": source_event_id,
            "sequence": source_sequence,
        }
        return self.archive(event, prepared)

    def reconcile(self) -> int:
        """Attempt verification for all latest accepted receipts."""

        verified = 0
        for receipt in list(self.receipts.latest().values()):
            if receipt.status != "accepted" or not receipt.openviking_uri:
                continue
            reconciled = self._try_reconcile(receipt)
            if reconciled is not None and reconciled.status == "verified":
                verified += 1
        return verified

    def _try_reconcile(self, receipt: ArchivalReceipt) -> ArchivalReceipt | None:
        uri = receipt.openviking_uri
        if receipt.ingestion_task_id:
            task = self._get_task(receipt.ingestion_task_id)
            if task:
                task_status = str(task.get("status", "")).lower()
                uri = (
                    _find_uri(task.get("result"))
                    or _find_uri(task)
                    or uri
                )
                if task_status in {"failed", "cancelled", "canceled"}:
                    failed = ArchivalReceipt(
                        **{
                            **receipt.to_dict(),
                            "status": "failed",
                            "openviking_uri": uri,
                            "archived_at": utc_now(),
                            "error": task.get("error")
                            or {
                                "type": "OpenVikingTaskError",
                                "message": f"Ingestion task ended as {task_status}",
                            },
                        }
                    )
                    self.receipts.append(failed)
                    return failed
                if task_status not in {"completed", "complete", "success", "succeeded"}:
                    return None
        readable_uri = self._resolve_readable_uri(uri)
        if readable_uri is None:
            return None
        verified = ArchivalReceipt(
            **{
                **receipt.to_dict(),
                "status": "verified",
                "openviking_uri": readable_uri,
                "archived_at": utc_now(),
                "error": None,
            }
        )
        self.receipts.append(verified)
        return verified

    def _get_task(self, task_id: str) -> dict[str, Any] | None:
        getter = getattr(self.client, "get_task", None)
        if not callable(getter):
            nested_client = getattr(self.client, "client", None)
            getter = getattr(nested_client, "get_task", None)
        if not callable(getter):
            return None
        try:
            result = getter(task_id)
        except Exception:
            return None
        return result if isinstance(result, dict) else None

    def _resolve_readable_uri(self, uri: str | None) -> str | None:
        if not uri:
            return None
        try:
            self.client.read(uri, offset=0, limit=1)
            return uri
        except Exception:
            pass

        lister = getattr(self.client, "ls", None)
        if not callable(lister):
            nested_client = getattr(self.client, "client", None)
            lister = getattr(nested_client, "ls", None)
        if not callable(lister):
            return None
        try:
            entries = lister(uri=uri, simple=False, recursive=False)
        except TypeError:
            entries = lister(uri)
        except Exception:
            return None
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict) or entry.get("isDir") is True:
                continue
            child_uri = entry.get("uri")
            if not isinstance(child_uri, str) or not child_uri.startswith("viking://"):
                continue
            try:
                self.client.read(child_uri, offset=0, limit=1)
            except Exception:
                continue
            return child_uri
        return None

    def _target_uri(
        self,
        run_id: str,
        sequence: int,
        artifact_id: str,
        suffix: str,
    ) -> str:
        safe_run = _safe_uri_component(run_id)
        safe_artifact = _safe_uri_component(artifact_id)
        safe_suffix = suffix if re.fullmatch(r"\.[A-Za-z0-9]+", suffix) else ""
        return (
            f"{self.base_uri}/{safe_run}/events/"
            f"{sequence:08d}/{safe_artifact}{safe_suffix}"
        )


class EventArchivalService:
    """Coordinate event reading, evidence upload, receipts, and enrichment."""

    def __init__(
        self,
        *,
        event_path: str | Path,
        run_dir: str | Path,
        state_dir: str | Path,
        client: OpenVikingClient,
        base_uri: str = "viking://resources/evidence/aid2e",
        verify_after_upload: bool = True,
    ) -> None:
        self.event_path = Path(event_path).expanduser().resolve()
        self.run_dir = Path(run_dir).expanduser().resolve()
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cursor_store = CursorStore(self.state_dir / "cursor.json")
        self.receipt_journal = ReceiptJournal(
            self.state_dir / "openviking_receipts.jsonl"
        )
        self.enriched_path = self.state_dir / "run_events.openviking.jsonl"
        self.archiver = OpenVikingArchiver(
            client,
            self.receipt_journal,
            base_uri=base_uri,
            verify_after_upload=verify_after_upload,
        )

    def process_once(self) -> dict[str, Any]:
        state = self.cursor_store.load()
        self.archiver.reconcile()
        reader = EventReader(self.event_path)
        events = list(reader.iter_events())
        processed = 0
        failures = 0

        for event in events:
            sequence = int(event["sequence"])
            if sequence <= state.last_archived_sequence:
                state.last_observed_sequence = max(
                    state.last_observed_sequence, sequence
                )
                continue
            state.run_id = state.run_id or str(event["run_id"])
            state.last_observed_sequence = max(
                state.last_observed_sequence, sequence
            )
            event_ok = True
            for evidence in event.get("evidence") or []:
                try:
                    prepared = prepare_evidence(
                        run_dir=self.run_dir,
                        state_dir=self.state_dir,
                        event=event,
                        evidence=evidence,
                    )
                    receipt = self.archiver.archive(event, prepared)
                    if receipt.status not in {"accepted", "verified"}:
                        event_ok = False
                except Exception:
                    event_ok = False
            if not event_ok:
                failures += 1
                break
            state.last_archived_sequence = sequence
            processed += 1

        state.last_verified_sequence = self._last_contiguous_verified(events)
        self.cursor_store.save(state)
        materialize_enriched_journal(
            self.event_path,
            self.receipt_journal.path,
            self.enriched_path,
        )

        final_receipt = None
        terminal = bool(events and events[-1].get("event_type") in TERMINAL_RUN_EVENTS)
        if terminal and state.last_verified_sequence == int(events[-1]["sequence"]):
            final_receipt = self.archiver.archive_file(
                run_id=str(events[-1]["run_id"]),
                source_event_id="__run_event_journal__",
                source_sequence=int(events[-1]["sequence"]),
                artifact_id="run-events-openviking",
                kind="enriched_event_journal",
                path=self.enriched_path,
            )

        return {
            "run_id": state.run_id,
            "processed_events": processed,
            "failures": failures,
            "last_observed_sequence": state.last_observed_sequence,
            "last_archived_sequence": state.last_archived_sequence,
            "last_verified_sequence": state.last_verified_sequence,
            "terminal": terminal,
            "enriched_journal": str(self.enriched_path),
            "final_journal_uri": (
                final_receipt.openviking_uri if final_receipt else None
            ),
            "final_journal_status": final_receipt.status if final_receipt else None,
        }

    def _last_contiguous_verified(self, events: list[dict[str, Any]]) -> int:
        latest = self.receipt_journal.latest().values()
        by_event: dict[str, list[ArchivalReceipt]] = {}
        for receipt in latest:
            by_event.setdefault(receipt.source_event_id, []).append(receipt)

        last_verified = 0
        for event in events:
            evidence = event.get("evidence") or []
            if evidence:
                receipts = by_event.get(str(event["event_id"]), [])
                verified_ids = {
                    item.artifact_id for item in receipts if item.status == "verified"
                }
                expected_ids = {str(item["artifact_id"]) for item in evidence}
                if verified_ids != expected_ids:
                    break
            last_verified = int(event["sequence"])
        return last_verified


def _raise_for_error_envelope(response: Any) -> None:
    if isinstance(response, dict) and response.get("ok") is False:
        error = response.get("error") or {}
        raise RuntimeError(str(error.get("message") or "OpenViking ingestion failed"))


def _find_uri(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith("viking://"):
        return value
    if isinstance(value, dict):
        for key in ("uri", "resource_uri", "target_uri"):
            found = value.get(key)
            if isinstance(found, str) and found.startswith("viking://"):
                return found
        for child in value.values():
            found = _find_uri(child)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        for child in value:
            found = _find_uri(child)
            if found:
                return found
    return None


def _find_identifier(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("task_id", "ingestion_id", "request_id"):
            found = value.get(key)
            if found is not None:
                return str(found)
        for child in value.values():
            found = _find_identifier(child)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        for child in value:
            found = _find_identifier(child)
            if found:
                return found
    return None


def _safe_uri_component(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-.")
    if not result:
        raise ValueError(f"Unsafe empty URI component from {value!r}")
    return result
