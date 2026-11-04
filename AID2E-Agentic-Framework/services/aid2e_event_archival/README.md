# AID2E Event Archival Helper

This deterministic helper is outside the core AID2E framework. It reads the
provider-neutral `run_events.jsonl`, sanitizes referenced local evidence,
uploads it with the existing OpenViking client, persists append-only receipts,
and atomically materializes `run_events.openviking.jsonl`.

It never modifies the framework-owned event journal. OpenViking failures are
recorded in helper state and do not change optimization state.

Run from the `AID2E-Agentic-Framework` repository root after loading the
existing OpenViking environment:

```bash
python -m services.aid2e_event_archival.cli \
  /path/to/run/run_events.jsonl \
  --state-dir /path/to/agent-state/run-id \
  --mode follow
```

The helper writes:

```text
<state-dir>/
|- cursor.json
|- openviking_receipts.jsonl
|- run_events.openviking.jsonl
`- sanitized/<run-id>/event-<sequence>/...
```
