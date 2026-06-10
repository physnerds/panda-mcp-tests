"""
AID2E MCP tools.

The tools are intentionally thin wrappers around the installed ``aid2e`` CLI.
They execute without a shell, keep the executable fixed, and return structured
stdout/stderr data that an MCP client can inspect.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional

from aid2e_service.app import mcp

DEFAULT_TIMEOUT_SECONDS = int(os.getenv("AID2E_COMMAND_TIMEOUT", "300"))
MAX_TIMEOUT_SECONDS = int(os.getenv("AID2E_MAX_COMMAND_TIMEOUT", "3600"))
DEFAULT_WORKDIR = Path(os.getenv("AID2E_WORKDIR", "/work"))
ALLOWED_WORKDIR_ROOTS = [
    Path(path).resolve()
    for path in os.getenv("AID2E_ALLOWED_WORKDIRS", "/work,/tmp,/opt/AID2E-framework")
    .split(",")
    if path.strip()
]


def _bounded_timeout(timeout: Optional[int]) -> int:
    if timeout is None:
        return DEFAULT_TIMEOUT_SECONDS
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")
    return min(timeout, MAX_TIMEOUT_SECONDS)


def _validate_args(args: list[str]) -> list[str]:
    clean_args = []
    for arg in args:
        if not isinstance(arg, str):
            raise ValueError("all arguments must be strings")
        if "\x00" in arg:
            raise ValueError("arguments cannot contain NUL bytes")
        clean_args.append(arg)
    return clean_args


def _resolve_workdir(cwd: Optional[str]) -> Path:
    workdir = Path(cwd).expanduser().resolve() if cwd else DEFAULT_WORKDIR
    for root in ALLOWED_WORKDIR_ROOTS:
        try:
            workdir.relative_to(root)
            break
        except ValueError:
            continue
    else:
        allowed = ", ".join(str(root) for root in ALLOWED_WORKDIR_ROOTS)
        raise ValueError(f"working directory must be under one of: {allowed}")

    if not workdir.exists():
        workdir.mkdir(parents=True, exist_ok=True)
    if not workdir.is_dir():
        raise ValueError(f"working directory is not a directory: {workdir}")
    return workdir


def _run_aid2e(args: list[str], timeout: Optional[int] = None, cwd: Optional[str] = None) -> dict:
    command = ["aid2e", *_validate_args(args)]
    workdir = _resolve_workdir(cwd)

    try:
        completed = subprocess.run(
            command,
            cwd=workdir,
            text=True,
            capture_output=True,
            timeout=_bounded_timeout(timeout),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "timed_out": True,
            "returncode": None,
            "command": command,
            "cwd": str(workdir),
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "error": f"aid2e command timed out after {exc.timeout} seconds",
        }

    return {
        "success": completed.returncode == 0,
        "timed_out": False,
        "returncode": completed.returncode,
        "command": command,
        "cwd": str(workdir),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@mcp.tool()
async def aid2e_version() -> dict:
    """
    Return the installed AID2E version information.

    This is the quickest health check for the AID2E CLI inside the MCP server
    container.
    """
    return _run_aid2e(["version"], timeout=30)


@mcp.tool()
async def aid2e_help(command: Optional[str] = None) -> dict:
    """
    Return AID2E CLI help text.

    Args:
        command: Optional subcommand name such as ``list``, ``validate``,
            ``describe``, ``inspect``, or ``optimize``. Leave empty for top-level
            ``aid2e --help``.
    """
    args = [command, "--help"] if command else ["--help"]
    return _run_aid2e(args, timeout=30)


@mcp.tool()
async def aid2e_list(kind: Optional[str] = None) -> dict:
    """
    List available AID2E optimizers, templates, or problem types.

    Args:
        kind: Optional list category accepted by the AID2E CLI. Examples depend
            on the installed AID2E branch; use ``aid2e_help("list")`` to inspect
            supported values.
    """
    args = ["list"]
    if kind:
        args.append(kind)
    return _run_aid2e(args, timeout=60)


@mcp.tool()
async def aid2e_run(args: list[str], timeout: Optional[int] = None, cwd: Optional[str] = None) -> dict:
    """
    Run an arbitrary AID2E CLI command with structured output.

    The executable is fixed to ``aid2e`` and arguments are passed without a
    shell. Use this for commands such as ``["validate", "config.yaml"]`` or
    ``["optimize", "config.yaml"]``.

    Args:
        args: Arguments passed after the ``aid2e`` executable.
        timeout: Optional timeout in seconds. Defaults to AID2E_COMMAND_TIMEOUT.
        cwd: Optional working directory. Defaults to AID2E_WORKDIR.
    """
    return _run_aid2e(args, timeout=timeout, cwd=cwd)
