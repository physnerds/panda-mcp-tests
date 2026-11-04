"""Compact optimization summaries and optional OpenViking session memory."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


SUMMARY_SYSTEM_PROMPT = (
    "You are an AID2E optimization monitoring agent. For every lifecycle event "
    "you observe, write exactly one factual sentence stating what changed, which "
    "run/trial/batch it concerns, its resulting state, and any important objective "
    "or error data present; never invent missing facts. When a trial reaches a "
    "terminal event, also write exactly one factual sentence summarizing that trial "
    "from its observed events. Keep detailed logs as evidence and cite their "
    "OpenViking URIs when available. These one-sentence records are compact L0-like "
    "orientation; OpenViking L1 is a directory overview, not a per-event sentence."
)


@dataclass(frozen=True)
class SummaryRecord:
    kind: str
    run_id: str
    sentence: str
    source_event_id: str
    source_sequence: int
    trial_index: int | None = None
    openviking_uri: str | None = None
    status: str = "local"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_one_sentence(text: str) -> str:
    """Normalize a model response and require exactly one prose sentence."""

    compact = " ".join(text.strip().split())
    compact = re.sub(r"^(?:[-*]\s+|summary:\s*)", "", compact, flags=re.I)
    if not compact:
        raise ValueError("summary is empty")
    sentences = [item for item in re.split(r"(?<=[.!?])\s+", compact) if item]
    if len(sentences) != 1:
        raise ValueError("summary must contain exactly one sentence")
    if compact[-1] not in ".!?":
        compact += "."
    return compact


def build_event_fallback(event: dict[str, Any]) -> str:
    """Produce a deterministic one-sentence summary when no LLM is available."""

    event_type = str(event.get("event_type", "unknown event"))
    run_id = str(event.get("run_id", "unknown run"))
    subject = f"trial {event['trial_index']}" if event.get("trial_index") is not None else (
        f"batch {event['batch_id']}" if event.get("batch_id") is not None else f"run {run_id}"
    )
    state = event.get("canonical_state") or event_type
    detail = ""
    if event.get("error"):
        error = event["error"]
        detail = f" with {error.get('error_type', 'an error')}: {error.get('message', 'no message')}"
    elif event.get("data", {}).get("objectives"):
        detail = f" with objectives {json.dumps(event['data']['objectives'], sort_keys=True)}"
    return ensure_one_sentence(
        f"AID2E event {event_type} placed {subject} in state {state}{detail}."
    )


def build_trial_fallback(events: Iterable[dict[str, Any]]) -> str:
    trial_events = list(events)
    if not trial_events:
        raise ValueError("trial summary requires at least one event")
    latest = trial_events[-1]
    trial = latest.get("trial_index")
    run_id = latest.get("run_id", "unknown run")
    state = latest.get("canonical_state") or latest.get("event_type", "unknown")
    return ensure_one_sentence(
        f"In AID2E run {run_id}, trial {trial} reached state {state} after {len(trial_events)} observed lifecycle events."
    )


def write_summary_record(state_dir: str | Path, record: SummaryRecord) -> Path:
    """Write one compact Markdown source and append its structured journal record."""

    root = Path(state_dir).expanduser().resolve() / "summaries"
    category = "trials" if record.kind == "trial_summary" else "events"
    identity = (
        f"trial-{record.trial_index:06d}"
        if record.trial_index is not None and record.kind == "trial_summary"
        else f"event-{record.source_sequence:08d}"
    )
    path = root / category / f"{identity}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.sentence + "\n", encoding="utf-8")
    journal = root / "summary_records.jsonl"
    with journal.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
    return path


def record_openviking_session(
    client: Any,
    *,
    run_id: str,
    records: Iterable[SummaryRecord],
) -> dict[str, Any] | None:
    """Commit summaries as a session so OpenViking may extract long-term memory."""

    target = getattr(client, "client", client)
    required = ("create_session", "add_message", "commit_session")
    if not all(callable(getattr(target, name, None)) for name in required):
        return None
    session_id = f"aid2e-{re.sub(r'[^A-Za-z0-9._-]+', '-', run_id)}"
    exists = getattr(target, "session_exists", None)
    if not callable(exists) or not exists(session_id):
        target.create_session(session_id=session_id)
    for record in records:
        source = {
            "run_id": record.run_id,
            "kind": record.kind,
            "source_event_id": record.source_event_id,
            "source_sequence": record.source_sequence,
            "trial_index": record.trial_index,
        }
        target.add_message(
            session_id=session_id,
            role="user",
            content="AID2E monitoring observation: " + json.dumps(source, sort_keys=True),
        )
        target.add_message(
            session_id=session_id,
            role="assistant",
            content=record.sentence,
        )
    result = target.commit_session(session_id=session_id)
    return {"session_id": session_id, "commit": result}
