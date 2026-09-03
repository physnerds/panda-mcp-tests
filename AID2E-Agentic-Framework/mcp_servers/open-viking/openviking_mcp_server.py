#!/usr/bin/env python3
"""FastMCP tools for the OpenViking service on aipanda106.cern.ch."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Optional

import uvicorn
from fastmcp import FastMCP

from openviking_client import (
    DEFAULT_API_KEY_FILE,
    DEFAULT_OPENVIKING_URL,
    OpenVikingAipandaClient,
)


DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 25901
DEFAULT_TRANSPORT = "streamable-http"

main_mcp = FastMCP(name="OpenViking")


def _client() -> OpenVikingAipandaClient:
    """Create a short-lived OpenViking client from environment configuration."""
    return OpenVikingAipandaClient(
        url=os.environ.get("OPENVIKING_URL", DEFAULT_OPENVIKING_URL),
        api_key_file=os.environ.get("OPENVIKING_API_KEY_FILE", str(DEFAULT_API_KEY_FILE)),
        require_ssl=os.environ.get("OPENVIKING_REQUIRE_SSL_ENV", "1").lower()
        not in {"0", "false", "no"},
    )


def _result(operation: str, arguments: dict[str, Any], data: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": operation,
        "arguments": arguments,
        "data": data,
    }


def _error(operation: str, arguments: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "isError": True,
        "operation": operation,
        "arguments": arguments,
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
    }


def _call_openviking(
    operation: str,
    arguments: dict[str, Any],
    callback: Callable[[OpenVikingAipandaClient], Any],
) -> dict[str, Any]:
    try:
        with _client() as client:
            return _result(operation, arguments, callback(client))
    except Exception as exc:
        return _error(operation, arguments, exc)


@main_mcp.tool
def openviking_find(query: str, target_uri: str = "", limit: int = 10) -> dict[str, Any]:
    """Semantic search over indexed OpenViking resources.

    Use this when a user asks for knowledge, documentation, prior context,
    memory, workflow rules, or resource discovery and does not already know the
    exact viking:// URI.

    Args:
        query: Search text describing the information needed.
        target_uri: Optional viking:// subtree to constrain the search.
        limit: Maximum number of matches to return.

    Returns:
        A JSON object with ok, operation, arguments, and data. The data field is
        the OpenViking search response and should preserve returned resource
        URIs for follow-up openviking_read calls.

    Common failures include missing SSL_CERT_FILE/SSL_CERT_DIR, missing API key,
    authentication failure, unavailable OpenViking backend, invalid target_uri,
    or an empty index.
    """
    arguments = {"query": query, "target_uri": target_uri, "limit": limit}
    return _call_openviking(
        "find",
        arguments,
        lambda client: client.find(query=query, target_uri=target_uri, limit=limit),
    )


@main_mcp.tool
def openviking_ls(
    uri: str = "viking://resources/",
    simple: bool = False,
    recursive: bool = False,
) -> dict[str, Any]:
    """List an OpenViking viking:// resource directory.

    Use this to discover available directories and files before assuming a
    resource path exists.

    Args:
        uri: viking:// directory or resource URI to list.
        simple: Return simplified listing entries when supported.
        recursive: Recursively list descendants when supported.

    Returns:
        A JSON object with ok, operation, arguments, and data. The data field is
        the OpenViking listing response.

    Common failures include missing SSL_CERT_FILE/SSL_CERT_DIR, missing API key,
    authentication failure, unavailable backend, or invalid uri.
    """
    arguments = {"uri": uri, "simple": simple, "recursive": recursive}
    return _call_openviking(
        "ls",
        arguments,
        lambda client: client.ls(uri=uri, simple=simple, recursive=recursive),
    )


@main_mcp.tool
def openviking_read(uri: str, offset: int = 0, limit: int = -1) -> dict[str, Any]:
    """Read exact content from an OpenViking viking:// resource URI.

    Use this after openviking_find or openviking_ls to ground answers in an
    exact resource instead of relying only on semantic search snippets.

    Args:
        uri: Exact viking:// resource URI to read.
        offset: Character or byte offset understood by OpenViking.
        limit: Maximum amount to read; -1 asks OpenViking for the full content.

    Returns:
        A JSON object with ok, operation, arguments, and data. The data field is
        the resource text returned by OpenViking.

    Common failures include missing SSL_CERT_FILE/SSL_CERT_DIR, missing API key,
    authentication failure, unavailable backend, invalid uri, or missing
    resource.
    """
    arguments = {"uri": uri, "offset": offset, "limit": limit}
    return _call_openviking(
        "read",
        arguments,
        lambda client: client.read(uri=uri, offset=offset, limit=limit),
    )


@main_mcp.tool
def openviking_abstract(uri: str) -> dict[str, Any]:
    """Get the OpenViking L0 abstract for a resource URI.

    Use this for quick orientation to a known resource before deciding whether
    an exact openviking_read call is needed.

    Args:
        uri: Exact viking:// resource URI.

    Returns:
        A JSON object with ok, operation, arguments, and data. The data field is
        the resource abstract text returned by OpenViking.

    Common failures include missing SSL_CERT_FILE/SSL_CERT_DIR, missing API key,
    authentication failure, unavailable backend, invalid uri, or missing
    abstract.
    """
    arguments = {"uri": uri}
    return _call_openviking(
        "abstract",
        arguments,
        lambda client: client.abstract(uri=uri),
    )


@main_mcp.tool
def openviking_overview(uri: str) -> dict[str, Any]:
    """Get the OpenViking L1 overview for a resource URI.

    Use this for a broader summary of a known resource or subtree. Prefer
    openviking_read when the final answer requires exact evidence.

    Args:
        uri: Exact viking:// resource URI or subtree URI.

    Returns:
        A JSON object with ok, operation, arguments, and data. The data field is
        the overview text returned by OpenViking.

    Common failures include missing SSL_CERT_FILE/SSL_CERT_DIR, missing API key,
    authentication failure, unavailable backend, invalid uri, or missing
    overview.
    """
    arguments = {"uri": uri}
    return _call_openviking(
        "overview",
        arguments,
        lambda client: client.overview(uri=uri),
    )


@main_mcp.tool
def openviking_add_resource(
    path: str,
    to: Optional[str] = None,
    parent: Optional[str] = None,
    wait: bool = False,
    timeout: Optional[float] = None,
) -> dict[str, Any]:
    """Add a filesystem resource to OpenViking.

    Use this to ingest documentation, workflow rules, sanitized logs, evidence,
    or memory files into the OpenViking knowledge layer. Do not ingest secrets,
    tokens, private keys, private certificates, or unsanitized sensitive logs.

    Args:
        path: Local filesystem path to ingest.
        to: Optional target viking:// URI or destination supported by OpenViking.
        parent: Optional parent viking:// URI supported by OpenViking.
        wait: Wait for ingestion completion when supported.
        timeout: Optional wait timeout in seconds.

    Returns:
        A JSON object with ok, operation, arguments, and data. The data field is
        the OpenViking ingestion response.

    Common failures include missing SSL_CERT_FILE/SSL_CERT_DIR, missing API key,
    authentication failure, unavailable backend, nonexistent path, invalid
    destination, or ingestion timeout.
    """
    arguments = {
        "path": path,
        "to": to,
        "parent": parent,
        "wait": wait,
        "timeout": timeout,
    }
    return _call_openviking(
        "add_resource",
        arguments,
        lambda client: client.add_resource(
            path=path,
            to=to,
            parent=parent,
            wait=wait,
            timeout=timeout,
        ),
    )


http_app = main_mcp.http_app(
    transport=os.environ.get("OPENVIKING_MCP_TRANSPORT", DEFAULT_TRANSPORT)
)


if __name__ == "__main__":
    uvicorn.run(
        http_app,
        host=os.environ.get("OPENVIKING_MCP_HOST", DEFAULT_HOST),
        port=int(os.environ.get("OPENVIKING_MCP_PORT", DEFAULT_PORT)),
    )
