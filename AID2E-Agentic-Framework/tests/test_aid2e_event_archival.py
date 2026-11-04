import json
import os
from pathlib import Path

import pytest

from services.aid2e_event_archival import EventArchivalService
from services.aid2e_event_archival.evidence import prepare_evidence
from services.aid2e_event_archival.journal import EventReader, ReceiptJournal


class FakeOpenVikingClient:
    def __init__(self, fail_uploads=0):
        self.fail_uploads = fail_uploads
        self.add_calls = []
        self.resources = {}
        self.tasks = {}

    def add_resource(self, path, to=None, parent=None, wait=False, timeout=None):
        self.add_calls.append((path, to, wait))
        if self.fail_uploads:
            self.fail_uploads -= 1
            raise RuntimeError("temporary OpenViking failure")
        self.resources[to] = Path(path).read_text(encoding="utf-8")
        task_id = f"task-{len(self.add_calls)}"
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "resource_id": to,
            "result": {"root_uri": to},
        }
        return {"task_id": task_id, "uri": to}

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def read(self, uri, offset=0, limit=-1):
        if uri not in self.resources:
            raise FileNotFoundError(uri)
        text = self.resources[uri]
        return text[offset:] if limit < 0 else text[offset : offset + limit]

    def ls(self, uri, simple=False, recursive=False):
        return [
            {"isDir": False, "name": Path(key).name, "uri": key}
            for key in self.resources
            if key.startswith(uri)
        ]


class FakeDirectoryOpenVikingClient(FakeOpenVikingClient):
    """Model OpenViking's directory target plus readable child behavior."""

    def add_resource(self, path, to=None, parent=None, wait=False, timeout=None):
        self.add_calls.append((path, to, wait))
        task_id = f"task-{len(self.add_calls)}"
        child_uri = f"{to}/{Path(path).stem}.md"
        self.resources[child_uri] = Path(path).read_text(encoding="utf-8")
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "resource_id": to,
            "result": {"root_uri": to},
        }
        return {"task_id": task_id, "uri": to}


def _write_terminal_run(run_dir):
    log_dir = run_dir / "trials" / "trial_0" / "log"
    log_dir.mkdir(parents=True)
    log_path = log_dir / "executor_demo_execution.log"
    log_path.write_text(
        "Authorization: Bearer secret-token\ntrial complete\n", encoding="utf-8"
    )
    event = {
        "schema_version": 1,
        "event_id": "event-1",
        "sequence": 1,
        "timestamp": "2026-11-03T20:00:00Z",
        "event_type": "run.completed",
        "entity_type": "run",
        "run_id": "demo-run",
        "canonical_state": "completed",
        "source": {"component": "test"},
        "evidence": [
            {
                "artifact_id": "trial-0-execution-log",
                "kind": "execution_log",
                "relative_path": "trials/trial_0/log/executor_demo_execution.log",
                "media_type": "text/plain",
                "mutable": False,
            }
        ],
        "data": {},
    }
    event_path = run_dir / "run_events.jsonl"
    event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return event_path, event


def test_end_to_end_archival_materializes_verified_uris(tmp_path):
    run_dir = tmp_path / "run"
    event_path, _ = _write_terminal_run(run_dir)
    state_dir = tmp_path / "state"
    client = FakeOpenVikingClient()
    service = EventArchivalService(
        event_path=event_path,
        run_dir=run_dir,
        state_dir=state_dir,
        client=client,
    )

    result = service.process_once()

    assert result["last_verified_sequence"] == 1
    assert result["terminal"] is True
    assert result["final_journal_status"] == "verified"
    enriched = json.loads(
        (state_dir / "run_events.openviking.jsonl").read_text(encoding="utf-8")
    )
    assert enriched["openviking"]["status"] == "verified"
    assert enriched["openviking"]["records"][0]["uri"].startswith("viking://")
    sanitized = next((state_dir / "sanitized").rglob("*.log"))
    assert "secret-token" not in sanitized.read_text(encoding="utf-8")
    assert "<REDACTED>" in sanitized.read_text(encoding="utf-8")

    calls_after_first_run = len(client.add_calls)
    repeated = service.process_once()
    assert repeated["processed_events"] == 0
    assert len(client.add_calls) == calls_after_first_run


def test_failed_upload_is_retried_without_advancing_archive_cursor(tmp_path):
    run_dir = tmp_path / "run"
    event_path, _ = _write_terminal_run(run_dir)
    state_dir = tmp_path / "state"
    client = FakeOpenVikingClient(fail_uploads=1)
    service = EventArchivalService(
        event_path=event_path,
        run_dir=run_dir,
        state_dir=state_dir,
        client=client,
    )

    failed = service.process_once()
    assert failed["failures"] == 1
    assert failed["last_archived_sequence"] == 0

    recovered = service.process_once()
    assert recovered["failures"] == 0
    assert recovered["last_archived_sequence"] == 1
    assert recovered["last_verified_sequence"] == 1
    attempts = [
        receipt.attempt
        for receipt in ReceiptJournal(
            state_dir / "openviking_receipts.jsonl"
        ).all()
        if receipt.source_event_id == "event-1"
    ]
    assert attempts == [1, 2, 2]


def test_receipt_resolves_directory_target_to_readable_child_uri(tmp_path):
    run_dir = tmp_path / "run"
    event_path, _ = _write_terminal_run(run_dir)
    state_dir = tmp_path / "state"
    service = EventArchivalService(
        event_path=event_path,
        run_dir=run_dir,
        state_dir=state_dir,
        client=FakeDirectoryOpenVikingClient(),
    )

    result = service.process_once()

    assert result["last_verified_sequence"] == 1
    receipt = next(
        item
        for item in ReceiptJournal(
            state_dir / "openviking_receipts.jsonl"
        ).all()
        if item.source_event_id == "event-1" and item.status == "verified"
    )
    assert receipt.openviking_uri.endswith(".md")


def test_resolver_rejects_path_escape(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    outside = tmp_path / "secret.log"
    outside.write_text("secret", encoding="utf-8")
    event = {"run_id": "demo", "sequence": 1}

    try:
        prepare_evidence(
            run_dir=run_dir,
            state_dir=tmp_path / "state",
            event=event,
            evidence={
                "artifact_id": "escape",
                "kind": "execution_log",
                "relative_path": "../secret.log",
            },
        )
    except ValueError as exc:
        assert "Unsafe evidence path" in str(exc)
    else:
        raise AssertionError("path traversal was accepted")


def test_event_reader_ignores_incomplete_final_record(tmp_path):
    event_path, event = _write_terminal_run(tmp_path / "run")
    with event_path.open("a", encoding="utf-8") as stream:
        stream.write('{"schema_version":1')

    assert list(EventReader(event_path).iter_events()) == [event]


@pytest.mark.skipif(
    not os.environ.get("AID2E_PHASE3_RUN_DIR"),
    reason="set AID2E_PHASE3_RUN_DIR for the real AID2E integration run",
)
def test_real_aid2e_run_archives_every_referenced_evidence(tmp_path):
    run_dir = Path(os.environ["AID2E_PHASE3_RUN_DIR"]).resolve()
    client = FakeOpenVikingClient()
    service = EventArchivalService(
        event_path=run_dir / "run_events.jsonl",
        run_dir=run_dir,
        state_dir=tmp_path / "state",
        client=client,
    )

    result = service.process_once()

    assert result["failures"] == 0
    assert result["last_verified_sequence"] == 23
    assert result["final_journal_status"] == "verified"
    enriched = [
        json.loads(line)
        for line in Path(result["enriched_journal"]).read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    referenced = sum(len(event.get("evidence") or []) for event in enriched)
    archived = sum(
        len(event["openviking"]["records"])
        for event in enriched
    )
    assert referenced == archived == 14
    assert all(
        event["openviking"]["status"] in {"not_required", "verified"}
        for event in enriched
    )
