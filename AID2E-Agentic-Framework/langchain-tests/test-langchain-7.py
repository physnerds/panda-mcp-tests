"""Launch, monitor, summarize, and archive an AID2E optimization.

Prerequisites:
  1. Start ``python -m mcp_servers.aid2e.aid2e_mcp_server``.
  2. Configure the BNL OpenAI-compatible model variables.
  3. Configure the existing OpenViking client/TLS variables.

The control loop calls the two AID2E MCP tools deterministically. LangChain
aggregates each trial's lifecycle events and creates one summary only after the
trial becomes terminal. OpenViking archival stays in the agent layer and never
enters AID2E core.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY))

from services.aid2e_event_archival import EventArchivalService
from services.aid2e_optimization_agent import (
    SUMMARY_SYSTEM_PROMPT,
    SummaryRecord,
    TrialEventAggregator,
    build_trial_fallback,
    ensure_one_sentence,
    record_openviking_session,
    write_summary_record,
)


DEFAULT_AID2E_MCP_URL = "http://127.0.0.1:25902/mcp/"
class OptimizationResponseSchema(BaseModel):
    """Compact final response, including all model usage for this run."""

    final_output: str = Field(description="Final optimization and upload result")
    tool_used: list[str] = Field(description="Tools used by the workflow")
    input_token: int = Field(description="Total summary-model input tokens")
    output_token: int = Field(description="Total summary-model output tokens")


@dataclass
class TokenUsage:
    """Accumulate LangChain AI-message usage without double counting."""

    input_tokens: int = 0
    output_tokens: int = 0

    def add_result(self, result: dict[str, Any]) -> tuple[int, int]:
        call_input = 0
        call_output = 0
        for message in result.get("messages", []):
            if not isinstance(message, AIMessage):
                continue
            usage = message.usage_metadata or {}
            if usage:
                call_input += int(
                    usage.get("input_tokens", usage.get("input_token", 0)) or 0
                )
                call_output += int(
                    usage.get("output_tokens", usage.get("output_token", 0)) or 0
                )
                continue

            # Some OpenAI-compatible endpoints expose usage only in response metadata.
            metadata = message.response_metadata or {}
            token_usage = metadata.get("token_usage") or metadata.get("usage") or {}
            call_input += int(
                token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0))
                or getattr(message, "input_tokens", 0)
                or 0
            )
            call_output += int(
                token_usage.get(
                    "completion_tokens", token_usage.get("output_tokens", 0)
                )
                or getattr(message, "output_tokens", 0)
                or 0
            )
        self.input_tokens += call_input
        self.output_tokens += call_output
        return call_input, call_output


def _tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    content = getattr(result, "content", result)
    if isinstance(content, list):
        for block in content:
            text = getattr(block, "text", None)
            if text:
                value = json.loads(text)
                if isinstance(value, dict):
                    return value
    if isinstance(content, str):
        value = json.loads(content)
        if isinstance(value, dict):
            return value
    if isinstance(result, dict):
        return result
    raise RuntimeError(f"Unsupported MCP result: {type(result)!r}")


def _unwrap(result: Any) -> dict[str, Any]:
    payload = _tool_payload(result)
    if payload.get("ok") is False:
        error = payload.get("error") or {}
        raise RuntimeError(error.get("message") or "AID2E MCP call failed")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("AID2E MCP response did not contain object data")
    return data


def _message_text(result: dict[str, Any]) -> str:
    message = result["messages"][-1]
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(item.get("text", item)) if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


async def _summarize_trial(
    agent: Any,
    trial_index: int,
    events: list[dict[str, Any]],
    *,
    usage: TokenUsage,
) -> str:
    fallback = build_trial_fallback(events)
    print(
        f"[summary] requesting terminal trial {trial_index}; "
        f"events={len(events)}",
        flush=True,
    )
    try:
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Summarize this terminal AID2E trial from all of its "
                            "observed lifecycle events in exactly one factual "
                            "sentence; include the resulting state and important "
                            "objective or error data, and do not invent missing "
                            "facts:\n"
                            + json.dumps(events, sort_keys=True)
                        ),
                    }
                ]
            }
        )
        call_input, call_output = usage.add_result(result)
        print(
            f"[summary] completed trial {trial_index}; "
            f"tokens input={call_input} output={call_output}",
            flush=True,
        )
        return ensure_one_sentence(_message_text(result))
    except Exception as exc:
        print(f"[summary] fallback for trial {trial_index}: {exc}", flush=True)
        return fallback


async def _summarize_and_archive_trial(
    *,
    agent: Any,
    trial_index: int,
    events: list[dict[str, Any]],
    usage: TokenUsage,
    run_id: str,
    state_dir: Path,
    archival: EventArchivalService,
) -> tuple[SummaryRecord, Any]:
    sentence = await _summarize_trial(
        agent,
        trial_index,
        events,
        usage=usage,
    )
    terminal_event = events[-1]
    record = SummaryRecord(
        kind="trial_summary",
        run_id=run_id,
        sentence=sentence,
        source_event_id=str(terminal_event["event_id"]),
        source_sequence=int(terminal_event["sequence"]),
        trial_index=trial_index,
    )
    path = write_summary_record(state_dir, record)
    receipt = archival.archiver.archive_file(
        run_id=run_id,
        source_event_id=f"__trial_summary__:{trial_index}",
        source_sequence=int(terminal_event["sequence"]),
        artifact_id=f"trial-{trial_index:06d}-summary",
        kind="trial_summary_l0_source",
        path=path,
    )
    stored_record = replace(
        record,
        openviking_uri=receipt.openviking_uri,
        status=receipt.status,
    )
    write_summary_record(state_dir, stored_record)
    return stored_record, receipt


def _print_receipt(receipt: Any, *, prefix: str = "upload") -> None:
    task = receipt.ingestion_task_id or "-"
    uri = receipt.openviking_uri or "-"
    print(
        f"[{prefix}] kind={receipt.kind} artifact={receipt.artifact_id} "
        f"status={receipt.status} task={task} uri={uri}",
        flush=True,
    )


def _print_new_receipts(archival: EventArchivalService, offset: int) -> int:
    receipts = archival.receipt_journal.all()
    for receipt in receipts[offset:]:
        _print_receipt(receipt)
    return len(receipts)


def _receipt_counts(archival: EventArchivalService) -> dict[str, int]:
    counts: dict[str, int] = {}
    for receipt in archival.receipt_journal.latest().values():
        counts[receipt.status] = counts.get(receipt.status, 0) + 1
    return counts


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _openviking_client_type():
    client_dir = REPOSITORY / "mcp_servers" / "open-viking"
    sys.path.insert(0, str(client_dir))
    from openviking_client import OpenVikingAipandaClient

    return OpenVikingAipandaClient


async def run_optimization_agent(
    *,
    config_path: Path,
    output_dir: Path,
    run_id: str,
    state_dir: Path,
    aid2e_mcp_url: str = DEFAULT_AID2E_MCP_URL,
    poll_seconds: float = 2.0,
    max_wait_seconds: float = 900.0,
    wait_for_verification: bool = False,
) -> dict[str, Any]:
    """Execute the complete launch-monitor-archive-memory workflow."""

    model = ChatOpenAI(
        model=os.environ.get("AID2E_AGENT_MODEL", "nemotron-3-ultra-550b-nvfp4"),
        base_url=os.environ["BNL_BASE_URL"],
        api_key=os.environ["BNL_API_KEY"],
    )
    summary_agent = create_agent(
        model=model,
        tools=[],
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        name="aid2e-optimization-monitor",
    )

    transport = StreamableHttpTransport(aid2e_mcp_url)
    records: list[SummaryRecord] = []
    trial_aggregator = TrialEventAggregator()
    usage = TokenUsage()
    cursor = 0
    started = time.monotonic()

    async with Client(transport) as aid2e_client:
        launch = _unwrap(
            await aid2e_client.call_tool(
                "aid2e_start_optimization",
                {
                    "config_path": str(config_path.resolve()),
                    "run_id": run_id,
                    "output_dir": str(output_dir.resolve()),
                    "verbosity": 2,
                },
            )
        )
        run_dir = Path(launch["run_dir"])
        print(
            f"[launch] run_id={run_id} status={launch.get('status', 'started')} "
            f"pid={launch.get('pid', '-')} run_dir={run_dir}",
            flush=True,
        )
        OpenVikingClient = _openviking_client_type()
        openviking_options = {}
        if os.environ.get("OPENVIKING_URL"):
            openviking_options["url"] = os.environ["OPENVIKING_URL"]
        if os.environ.get("OPENVIKING_API_KEY_FILE"):
            openviking_options["api_key_file"] = os.environ[
                "OPENVIKING_API_KEY_FILE"
            ]
        with OpenVikingClient(**openviking_options) as openviking:
            archival = EventArchivalService(
                event_path=run_dir / "run_events.jsonl",
                run_dir=run_dir,
                state_dir=state_dir,
                client=openviking,
                base_uri="viking://resources/evidence/aid2e",
            )
            terminal = False
            latest_status: dict[str, Any] = {}
            receipt_offset = 0
            while not terminal:
                if time.monotonic() - started > max_wait_seconds:
                    raise TimeoutError(f"AID2E run {run_id} did not finish in time")
                latest_status = _unwrap(
                    await aid2e_client.call_tool(
                        "aid2e_read_optimization",
                        {
                            "run_id": run_id,
                            "output_dir": str(output_dir.resolve()),
                            "cursor": cursor,
                            "limit": 100,
                        },
                    )
                )
                archival_result = archival.process_once()
                receipt_offset = _print_new_receipts(archival, receipt_offset)
                print(
                    f"[monitor] elapsed={time.monotonic() - started:.1f}s "
                    f"status={latest_status['status']} "
                    f"new_events={len(latest_status['events'])} cursor={cursor} "
                    f"archived={archival_result['last_archived_sequence']} "
                    f"verified={archival_result['last_verified_sequence']}",
                    flush=True,
                )
                for event in latest_status["events"]:
                    cursor = max(cursor, int(event["sequence"]))
                    print(
                        f"[event] sequence={event['sequence']} "
                        f"type={event['event_type']} trial={event.get('trial_index')}",
                        flush=True,
                    )
                    terminal_trial = trial_aggregator.observe(event)
                    if terminal_trial is not None:
                        index, observed_events = terminal_trial
                        stored_record, _ = await _summarize_and_archive_trial(
                            agent=summary_agent,
                            trial_index=index,
                            events=observed_events,
                            usage=usage,
                            run_id=run_id,
                            state_dir=state_dir,
                            archival=archival,
                        )
                        receipt_offset = _print_new_receipts(
                            archival, receipt_offset
                        )
                        records.append(stored_record)

                terminal = bool(
                    latest_status["terminal"] and not latest_status["has_more"]
                )
                if not terminal:
                    if not latest_status["has_more"]:
                        await asyncio.sleep(max(poll_seconds, 0.1))

            # Process the terminal event evidence. OpenViking acceptance is the
            # default upload boundary; strict background verification is optional.
            archival_result = archival.process_once()
            receipt_offset = _print_new_receipts(archival, receipt_offset)
            if archival_result["failures"]:
                raise RuntimeError("OpenViking evidence archival failed")
            if archival_result["last_archived_sequence"] < cursor:
                raise RuntimeError(
                    "Not all AID2E event evidence was accepted by OpenViking"
                )

            auxiliary_receipts = []
            for artifact_id, kind, path_text in (
                (
                    "aid2e-framework-log",
                    "aid2e_framework_log",
                    latest_status["framework_log"],
                ),
                (
                    "aid2e-process-log",
                    "aid2e_process_log",
                    latest_status["process_log"],
                ),
            ):
                path = Path(path_text)
                if not path.is_file():
                    raise RuntimeError(f"Required AID2E log is missing: {path}")
                receipt = archival.archiver.archive_file(
                    run_id=run_id,
                    source_event_id=f"__{artifact_id}__",
                    source_sequence=cursor,
                    artifact_id=artifact_id,
                    kind=kind,
                    path=path,
                )
                receipt_offset = _print_new_receipts(
                    archival, receipt_offset
                )
                if receipt.status not in {"accepted", "verified"}:
                    raise RuntimeError(
                        f"OpenViking did not accept {artifact_id}: {receipt.error}"
                    )
                auxiliary_receipts.append(receipt.to_dict())

            # Upload the accepted-state monitoring journal now. The archival
            # service may later publish its canonical verified-state journal.
            monitoring_receipt = archival.archiver.archive_file(
                run_id=run_id,
                source_event_id="__accepted_run_event_journal__",
                source_sequence=cursor,
                artifact_id="run-events-openviking-accepted",
                kind="accepted_enriched_event_journal",
                path=archival.enriched_path,
            )
            receipt_offset = _print_new_receipts(archival, receipt_offset)
            if monitoring_receipt.status not in {"accepted", "verified"}:
                raise RuntimeError(
                    "OpenViking did not accept the monitoring event journal"
                )

            if wait_for_verification:
                print(
                    "[verify] strict mode enabled; waiting for the canonical "
                    "enriched event journal to be verified",
                    flush=True,
                )
                while archival_result["final_journal_status"] != "verified":
                    if time.monotonic() - started > max_wait_seconds:
                        raise TimeoutError(
                            "OpenViking did not verify the enriched event journal "
                            "in time; rerun without "
                            "AID2E_WAIT_FOR_OPENVIKING_VERIFICATION=1 to stop "
                            "after upload acceptance"
                        )
                    await asyncio.sleep(max(poll_seconds, 0.1))
                    archival_result = archival.process_once()
                    receipt_offset = _print_new_receipts(
                        archival, receipt_offset
                    )
                    counts = _receipt_counts(archival)
                    print(
                        f"[verify] verified_sequence="
                        f"{archival_result['last_verified_sequence']}/{cursor} "
                        f"accepted={counts.get('accepted', 0)} "
                        f"verified={counts.get('verified', 0)}",
                        flush=True,
                    )

            receipt_counts = _receipt_counts(archival)
            failed_uploads = receipt_counts.get("failed", 0)
            if failed_uploads:
                raise RuntimeError(
                    f"OpenViking reported {failed_uploads} failed upload(s)"
                )
            print(
                f"[upload] all logs accepted; accepted="
                f"{receipt_counts.get('accepted', 0)} "
                f"verified={receipt_counts.get('verified', 0)}",
                flush=True,
            )
            print(
                f"[memory] committing {len(records)} summary records for {run_id}",
                flush=True,
            )
            memory = record_openviking_session(
                openviking,
                run_id=run_id,
                records=records,
            )
            print(
                f"[memory] commit {'completed' if memory else 'not supported'}",
                flush=True,
            )

    return {
        "run_id": run_id,
        "status": latest_status["status"],
        "run_dir": str(run_dir),
        "event_summaries": sum(item.kind == "event_summary" for item in records),
        "trial_summaries": sum(item.kind == "trial_summary" for item in records),
        "summary_uploads": len(records),
        "summary_records": [item.to_dict() for item in records],
        "archival": archival_result,
        "monitoring_journal_receipt": monitoring_receipt.to_dict(),
        "auxiliary_receipts": auxiliary_receipts,
        "openviking_receipt_counts": receipt_counts,
        "openviking_memory_session": memory,
        "token_usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    }


async def main() -> None:
    aid2e_repository = Path(
        os.environ.get(
            "AID2E_REPOSITORY",
            REPOSITORY.parent / "AID2E-framework",
        )
    )
    run_id = os.environ.get("AID2E_AGENT_RUN_ID", f"agent-dtlz2-{int(time.time())}")
    output_dir = Path(os.environ.get("AID2E_AGENT_OUTPUT_DIR", "/tmp/aid2e-agent-runs"))
    result = await run_optimization_agent(
        config_path=Path(
            os.environ.get(
                "AID2E_AGENT_CONFIG",
                aid2e_repository / "examples/monitoring/dtlz2_joblib_events.yml",
            )
        ),
        output_dir=output_dir,
        run_id=run_id,
        state_dir=Path(
            os.environ.get("AID2E_AGENT_STATE_ROOT", "/tmp/aid2e-agent-state")
        )
        / run_id,
        aid2e_mcp_url=os.environ.get("AID2E_MCP_URL", DEFAULT_AID2E_MCP_URL),
        wait_for_verification=_env_flag(
            "AID2E_WAIT_FOR_OPENVIKING_VERIFICATION"
        ),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    counts = result["openviking_receipt_counts"]
    pending = counts.get("accepted", 0)
    verification_note = (
        f"; {pending} upload(s) remain in OpenViking background verification"
        if pending
        else "; all uploads are verified"
    )
    response = OptimizationResponseSchema(
        final_output=(
            f"Optimization {result['run_id']} finished with status "
            f"{result['status']}; all logs were accepted by OpenViking"
            f"{verification_note}."
        ),
        tool_used=[
            "aid2e_start_optimization",
            "aid2e_read_optimization",
            "openviking_add_resource",
        ],
        input_token=result["token_usage"]["input_tokens"],
        output_token=result["token_usage"]["output_tokens"],
    )
    print("\nFinal optimization report", flush=True)
    print(response.model_dump_json(indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
