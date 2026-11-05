import json
import sys
import time
from pathlib import Path

import pytest

from mcp_servers.aid2e.runtime import AID2ERuntime, RuntimeSettings
from services.aid2e_optimization_agent import (
    SummaryRecord,
    TrialEventAggregator,
    build_event_fallback,
    build_trial_fallback,
    ensure_one_sentence,
    record_openviking_session,
    write_summary_record,
)


def _fake_runtime(tmp_path: Path) -> tuple[AID2ERuntime, Path, Path]:
    repository = tmp_path / "aid2e"
    repository.mkdir()
    config = repository / "optimization.yml"
    config.write_text("problem: {}\n", encoding="utf-8")
    output = tmp_path / "runs"
    script = tmp_path / "fake_aid2e.py"
    script.write_text(
        """
import argparse, json
from pathlib import Path

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('operation')
parser.add_argument('config')
parser.add_argument('--output')
parser.add_argument('--run-id')
parser.add_argument('--log')
args, _ = parser.parse_known_args()
run_dir = Path(args.output) / args.run_id
run_dir.mkdir(parents=True, exist_ok=True)
Path(args.log).write_text('framework completed\\n', encoding='utf-8')
events = [
  {'schema_version': 1, 'event_id': 'e1', 'sequence': 1,
   'event_type': 'run.started', 'entity_type': 'run', 'run_id': args.run_id,
   'canonical_state': 'running', 'evidence': [], 'data': {}},
  {'schema_version': 1, 'event_id': 'e2', 'sequence': 2,
   'event_type': 'trial.completed', 'entity_type': 'trial', 'run_id': args.run_id,
   'trial_index': 0, 'canonical_state': 'completed', 'evidence': [], 'data': {}},
  {'schema_version': 1, 'event_id': 'e3', 'sequence': 3,
   'event_type': 'run.completed', 'entity_type': 'run', 'run_id': args.run_id,
   'canonical_state': 'completed', 'evidence': [], 'data': {}},
]
with (run_dir / 'run_events.jsonl').open('w', encoding='utf-8') as stream:
    for event in events:
        stream.write(json.dumps(event) + '\\n')
""".lstrip(),
        encoding="utf-8",
    )
    settings = RuntimeSettings(
        repository=repository,
        config_roots=(repository,),
        output_roots=(output.resolve(),),
        command=(sys.executable, str(script)),
    )
    return AID2ERuntime(settings), config, output


def test_runtime_launches_and_reads_incremental_events(tmp_path):
    runtime, config, output = _fake_runtime(tmp_path)

    launch = runtime.start_optimization(
        config_path=str(config), run_id="agent-test", output_dir=str(output)
    )
    deadline = time.monotonic() + 5
    result = None
    while time.monotonic() < deadline:
        result = runtime.read_optimization(
            run_id="agent-test", output_dir=str(output), cursor=0, limit=2
        )
        if result["events"]:
            break
        time.sleep(0.02)

    assert launch["status"] == "starting"
    assert result is not None
    assert [item["sequence"] for item in result["events"]] == [1, 2]
    assert result["next_cursor"] == 2
    assert result["has_more"] is True

    final = runtime.read_optimization(
        run_id="agent-test", output_dir=str(output), cursor=2
    )
    assert [item["sequence"] for item in final["events"]] == [3]
    assert final["terminal"] is True
    assert final["status"] == "completed"
    assert Path(final["framework_log"]).read_text() == "framework completed\n"


def test_runtime_rejects_unsafe_paths_and_duplicate_runs(tmp_path):
    runtime, config, output = _fake_runtime(tmp_path)
    outside = tmp_path / "outside.yml"
    outside.write_text("problem: {}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="CONFIG_ROOTS"):
        runtime.start_optimization(
            config_path=str(outside), run_id="safe", output_dir=str(output)
        )
    with pytest.raises(ValueError, match="run_id"):
        runtime.start_optimization(
            config_path=str(config), run_id="../escape", output_dir=str(output)
        )

    runtime.start_optimization(
        config_path=str(config), run_id="duplicate", output_dir=str(output)
    )
    with pytest.raises(FileExistsError):
        runtime.start_optimization(
            config_path=str(config), run_id="duplicate", output_dir=str(output)
        )


def test_summary_contract_and_files(tmp_path):
    event = {
        "event_id": "event-1",
        "sequence": 4,
        "event_type": "trial.completed",
        "run_id": "demo",
        "trial_index": 2,
        "canonical_state": "completed",
        "data": {"objectives": {"f1": 0.2, "f2": 0.8}},
    }
    event_sentence = build_event_fallback(event)
    trial_sentence = build_trial_fallback([event])
    assert ensure_one_sentence(event_sentence) == event_sentence
    assert ensure_one_sentence(trial_sentence) == trial_sentence
    with pytest.raises(ValueError, match="exactly one"):
        ensure_one_sentence("First sentence. Second sentence.")

    record = SummaryRecord(
        kind="trial_summary",
        run_id="demo",
        sentence=trial_sentence,
        source_event_id="event-1",
        source_sequence=4,
        trial_index=2,
    )
    path = write_summary_record(tmp_path, record)
    assert path.read_text(encoding="utf-8") == trial_sentence + "\n"
    journal_record = json.loads(
        (tmp_path / "summaries" / "summary_records.jsonl").read_text()
    )
    assert journal_record["trial_index"] == 2


def test_trial_event_aggregator_yields_one_terminal_history_per_trial():
    aggregator = TrialEventAggregator()
    assert aggregator.observe(
        {"event_type": "run.started", "trial_index": None}
    ) is None
    assert aggregator.observe(
        {"event_type": "trial.suggested", "trial_index": 3, "sequence": 1}
    ) is None
    assert aggregator.observe(
        {"event_type": "trial.started", "trial_index": 3, "sequence": 2}
    ) is None

    terminal = aggregator.observe(
        {"event_type": "trial.completed", "trial_index": 3, "sequence": 3}
    )
    assert terminal is not None
    index, events = terminal
    assert index == 3
    assert [event["sequence"] for event in events] == [1, 2, 3]

    assert aggregator.observe(
        {"event_type": "trial.completed", "trial_index": 3, "sequence": 4}
    ) is None
    failed = aggregator.observe(
        {"event_type": "trial.failed", "trial_index": 4, "sequence": 5}
    )
    assert failed is not None
    assert failed[0] == 4


class _FakeSessionClient:
    def __init__(self):
        self.created = []
        self.messages = []
        self.committed = []

    def create_session(self, session_id):
        self.created.append(session_id)
        return {"session_id": session_id}

    def add_message(self, session_id, role, content):
        self.messages.append((session_id, role, content))

    def commit_session(self, session_id):
        self.committed.append(session_id)
        return {"status": "accepted"}


def test_summary_records_can_be_committed_as_openviking_session():
    client = _FakeSessionClient()
    record = SummaryRecord(
        kind="event_summary",
        run_id="demo",
        sentence="AID2E run demo started.",
        source_event_id="event-1",
        source_sequence=1,
    )

    result = record_openviking_session(client, run_id="demo", records=[record])

    assert result["session_id"] == "aid2e-demo"
    assert len(client.messages) == 2
    assert client.messages[0][1] == "user"
    assert client.messages[1][1] == "assistant"
    assert client.committed == ["aid2e-demo"]
