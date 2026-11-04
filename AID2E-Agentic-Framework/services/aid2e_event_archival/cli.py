"""CLI for the external AID2E-to-OpenViking event archival helper."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .archiver import EventArchivalService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Archive AID2E event evidence in OpenViking."
    )
    parser.add_argument("event_path", help="Path to AID2E run_events.jsonl")
    parser.add_argument("--run-dir", help="Run root; defaults to event parent")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument(
        "--base-uri", default="viking://resources/evidence/aid2e"
    )
    parser.add_argument(
        "--mode", choices=("once", "follow", "resume", "reconcile"), default="once"
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--no-verify", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    event_path = Path(args.event_path).expanduser().resolve()
    client_dir = Path(__file__).resolve().parents[2] / "mcp_servers" / "open-viking"
    sys.path.insert(0, str(client_dir))
    from openviking_client import OpenVikingAipandaClient

    with OpenVikingAipandaClient() as client:
        service = EventArchivalService(
            event_path=event_path,
            run_dir=Path(args.run_dir).expanduser().resolve() if args.run_dir else event_path.parent,
            state_dir=args.state_dir,
            client=client,
            base_uri=args.base_uri,
            verify_after_upload=not args.no_verify,
        )
        while True:
            result = service.process_once()
            print(json.dumps(result, indent=2, sort_keys=True), flush=True)
            if args.mode != "follow":
                return 0 if not result["failures"] else 1
            if (
                result["terminal"]
                and result["final_journal_status"] == "verified"
            ):
                return 0
            time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
