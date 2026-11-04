"""Safe process and event-journal adapter used by the AID2E MCP server."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_EVENTS = {
    "run.completed",
    "run.completed_with_failures",
    "run.failed",
    "run.cancelled",
}
RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_repository() -> Path:
    return Path(__file__).resolve().parents[3] / "AID2E-framework"


def _path_list(name: str, default: list[Path]) -> tuple[Path, ...]:
    raw = os.environ.get(name)
    values = [Path(item) for item in raw.split(os.pathsep)] if raw else default
    return tuple(item.expanduser().resolve() for item in values)


def _within(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


@dataclass(frozen=True)
class RuntimeSettings:
    repository: Path
    config_roots: tuple[Path, ...]
    output_roots: tuple[Path, ...]
    command: tuple[str, ...]

    @classmethod
    def from_environment(cls) -> "RuntimeSettings":
        repository = Path(
            os.environ.get("AID2E_REPOSITORY", _default_repository())
        ).expanduser().resolve()
        default_command = repository / ".venv" / "bin" / "aid2e"
        command_text = os.environ.get(
            "AID2E_COMMAND",
            str(default_command) if default_command.is_file() else "aid2e",
        )
        command = tuple(shlex.split(command_text))
        if not command:
            raise RuntimeError("AID2E_COMMAND must contain an executable")
        return cls(
            repository=repository,
            config_roots=_path_list("AID2E_ALLOWED_CONFIG_ROOTS", [repository]),
            output_roots=_path_list(
                "AID2E_ALLOWED_OUTPUT_ROOTS", [Path("/tmp/aid2e-agent-runs")]
            ),
            command=command,
        )


class AID2ERuntime:
    """Launch authorized AID2E runs and read their append-only event journals."""

    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        self.settings = settings or RuntimeSettings.from_environment()
        self._processes: dict[int, subprocess.Popen[bytes]] = {}

    def start_optimization(
        self,
        *,
        config_path: str,
        run_id: str,
        output_dir: str = "",
        workflow_name: str = "",
        verbosity: int = 1,
    ) -> dict[str, Any]:
        """Start one nonblocking AID2E CLI optimization."""

        config = Path(config_path).expanduser().resolve()
        if not config.is_file() or config.suffix.lower() not in {".yml", ".yaml"}:
            raise ValueError("config_path must name an existing YAML file")
        if not _within(config, self.settings.config_roots):
            raise ValueError("config_path is outside AID2E_ALLOWED_CONFIG_ROOTS")
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError(
                "run_id must be 1-128 characters using letters, digits, '.', '_' or '-'"
            )
        if not 0 <= verbosity <= 3:
            raise ValueError("verbosity must be between 0 and 3")

        output_root = Path(output_dir).expanduser().resolve() if output_dir else self.settings.output_roots[0]
        if not _within(output_root, self.settings.output_roots):
            raise ValueError("output_dir is outside AID2E_ALLOWED_OUTPUT_ROOTS")
        run_dir = (output_root / run_id).resolve()
        if output_root not in run_dir.parents:
            raise ValueError("run_id escapes output_dir")
        metadata_path = run_dir / ".aid2e_agent_launch.json"
        event_path = run_dir / "run_events.jsonl"
        if metadata_path.exists() or event_path.exists():
            raise FileExistsError(f"run_id already exists: {run_id}")

        run_dir.mkdir(parents=True, exist_ok=True)
        process_log = run_dir / "aid2e_process.log"
        framework_log = run_dir / "aid2e_framework.log"
        command = [
            *self.settings.command,
            "optimize",
            str(config),
            "--output",
            str(output_root),
            "--run-id",
            run_id,
            "--log",
            str(framework_log),
        ]
        command.extend(["-" + "v" * verbosity] if verbosity else [])
        if workflow_name:
            command.extend(["--workflow", workflow_name])

        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"
        with process_log.open("ab", buffering=0) as stream:
            process = subprocess.Popen(
                command,
                cwd=self.settings.repository,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        self._processes[process.pid] = process
        metadata = {
            "schema_version": 1,
            "started_at": _utc_now(),
            "pid": process.pid,
            "run_id": run_id,
            "config_path": str(config),
            "output_dir": str(output_root),
            "run_dir": str(run_dir),
            "event_path": str(event_path),
            "framework_log": str(framework_log),
            "process_log": str(process_log),
            "command": command,
        }
        _atomic_json(metadata_path, metadata)
        return {**metadata, "status": "starting"}

    def read_optimization(
        self,
        *,
        run_id: str,
        output_dir: str = "",
        cursor: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return lifecycle events after a cursor plus process/run status."""

        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("invalid run_id")
        if cursor < 0:
            raise ValueError("cursor must be non-negative")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        output_root = Path(output_dir).expanduser().resolve() if output_dir else self.settings.output_roots[0]
        if not _within(output_root, self.settings.output_roots):
            raise ValueError("output_dir is outside AID2E_ALLOWED_OUTPUT_ROOTS")
        run_dir = (output_root / run_id).resolve()
        metadata_path = run_dir / ".aid2e_agent_launch.json"
        if not metadata_path.is_file():
            raise FileNotFoundError(f"unknown agent-launched run: {run_id}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        events = self._read_events(run_dir / "run_events.jsonl")
        selected = [event for event in events if int(event["sequence"]) > cursor][
            :limit
        ]
        latest = events[-1] if events else None
        terminal = bool(latest and latest.get("event_type") in TERMINAL_EVENTS)
        pid = int(metadata["pid"])
        process_state, return_code = self._process_state(pid)
        if terminal:
            status = str(latest.get("canonical_state") or latest["event_type"])
        elif process_state == "exited":
            status = "process_exited_without_terminal_event"
        elif events:
            status = str(latest.get("canonical_state") or "running")
        else:
            status = "starting"
        next_cursor = int(selected[-1]["sequence"]) if selected else cursor
        return {
            "run_id": run_id,
            "status": status,
            "terminal": terminal,
            "process_state": process_state,
            "return_code": return_code,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": bool(events and int(events[-1]["sequence"]) > next_cursor),
            "events": selected,
            "latest_event": latest,
            "run_dir": str(run_dir),
            "event_path": str(run_dir / "run_events.jsonl"),
            "framework_log": metadata["framework_log"],
            "process_log": metadata["process_log"],
        }

    def _process_state(self, pid: int) -> tuple[str, int | None]:
        process = self._processes.get(pid)
        if process is not None:
            result = process.poll()
            return ("running", None) if result is None else ("exited", result)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "exited", None
        except PermissionError:
            return "unknown", None
        return "running", None

    @staticmethod
    def _read_events(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as stream:
            while True:
                line = stream.readline()
                if not line:
                    break
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    if not line.endswith("\n"):
                        break
                    raise
                if not isinstance(event, dict) or "sequence" not in event:
                    raise RuntimeError(f"Invalid event record in {path}")
                events.append(event)
        return events
