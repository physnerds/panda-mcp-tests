#!/usr/bin/env python3
"""Minimal FastMCP surface for launching and observing AID2E optimizations."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

import uvicorn
from fastmcp import FastMCP

if __package__:
    from .runtime import AID2ERuntime
else:
    # Support ``python aid2e_mcp_server.py`` from this directory as well as the
    # preferred ``python -m mcp_servers.aid2e.aid2e_mcp_server`` form.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from runtime import AID2ERuntime


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 25902
main_mcp = FastMCP(name="AID2E")
_runtime_instance: AID2ERuntime | None = None


def _runtime() -> AID2ERuntime:
    global _runtime_instance
    if _runtime_instance is None:
        _runtime_instance = AID2ERuntime()
    return _runtime_instance


def _call(operation: str, arguments: dict[str, Any], callback: Callable[[], Any]) -> dict[str, Any]:
    try:
        return {"ok": True, "operation": operation, "arguments": arguments, "data": callback()}
    except Exception as exc:
        return {
            "ok": False,
            "isError": True,
            "operation": operation,
            "arguments": arguments,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


@main_mcp.tool
def aid2e_start_optimization(
    config_path: str,
    run_id: str,
    output_dir: str = "",
    workflow_name: str = "",
    verbosity: int = 1,
) -> dict[str, Any]:
    """Start one authorized AID2E optimization without blocking.

    Use this only when the user has authorized launching an optimization.
    config_path must be an existing YAML file below AID2E_ALLOWED_CONFIG_ROOTS;
    output_dir must be below AID2E_ALLOWED_OUTPUT_ROOTS. run_id must be unique.
    Returns the PID, run directory, event path, and framework/process log paths.
    Common failures are unsafe paths, duplicate run IDs, or a missing executable.
    """
    arguments = {
        "config_path": config_path,
        "run_id": run_id,
        "output_dir": output_dir,
        "workflow_name": workflow_name,
        "verbosity": verbosity,
    }
    return _call(
        "start_optimization",
        arguments,
        lambda: _runtime().start_optimization(**arguments),
    )


@main_mcp.tool
def aid2e_read_optimization(
    run_id: str,
    output_dir: str = "",
    cursor: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Read incremental lifecycle events and current status for one AID2E run.

    Pass the next_cursor from the previous response to avoid rereading events.
    The response includes terminal/process status, event evidence references,
    run paths, and has_more. It never mutates or controls the optimization.
    Common failures are unknown runs, unsafe output paths, or invalid cursors.
    """
    arguments = {
        "run_id": run_id,
        "output_dir": output_dir,
        "cursor": cursor,
        "limit": limit,
    }
    return _call(
        "read_optimization",
        arguments,
        lambda: _runtime().read_optimization(**arguments),
    )


http_app = main_mcp.http_app(transport="streamable-http")


if __name__ == "__main__":
    uvicorn.run(
        http_app,
        host=os.environ.get("AID2E_MCP_HOST", DEFAULT_HOST),
        port=int(os.environ.get("AID2E_MCP_PORT", DEFAULT_PORT)),
    )
