#!/usr/bin/env python3
"""Direct validation client for the deployed SWF Testbed MCP endpoint."""

import argparse
import asyncio
import json
import os

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from swf_testbed_agent import (
    DEFAULT_MCP_URL,
    DEFAULT_TOKEN_ENV,
    PANDAMON_TOOL_ALLOWLIST,
)


def parse_value(raw_value: str):
    """Parse JSON-compatible CLI values while preserving ordinary strings."""
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return raw_value


def parse_args():
    parser = argparse.ArgumentParser(
        description="Test the deployed SWF Testbed PanDAMon MCP tools"
    )
    parser.add_argument(
        "--mcp-url",
        default=DEFAULT_MCP_URL,
        help=f"MCP endpoint URL (default: {DEFAULT_MCP_URL})",
    )
    parser.add_argument(
        "--token-env",
        default=DEFAULT_TOKEN_ENV,
        help=f"Environment variable containing the bearer token (default: {DEFAULT_TOKEN_ENV})",
    )
    parser.add_argument("--list-tools", action="store_true", help="List tools")
    parser.add_argument(
        "--allowed-only",
        action="store_true",
        help="When listing, show only the approved PanDAMon tools",
    )
    parser.add_argument("--tool", help="Approved PanDAMon tool to invoke")
    parser.add_argument(
        "--kv",
        metavar="KEY=VALUE",
        action="append",
        default=[],
        help="Tool argument; VALUE may be JSON and the option may be repeated",
    )
    args = parser.parse_args()

    if not args.list_tools and not args.tool:
        parser.error("specify --list-tools or --tool")
    if args.allowed_only and not args.list_tools:
        parser.error("--allowed-only requires --list-tools")
    return args


def parse_arguments(parser, items):
    arguments = {}
    for item in items:
        if "=" not in item:
            parser.error(f"invalid --kv value {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        if not key:
            parser.error("tool argument names cannot be empty")
        arguments[key] = parse_value(value)
    return arguments


async def main():
    args = parse_args()
    token = os.getenv(args.token_env)
    if not token:
        raise SystemExit(
            f"Missing bearer token. Set environment variable {args.token_env}."
        )

    parser = argparse.ArgumentParser(add_help=False)
    arguments = parse_arguments(parser, args.kv)

    if args.tool and args.tool not in PANDAMON_TOOL_ALLOWLIST:
        allowed = ", ".join(sorted(PANDAMON_TOOL_ALLOWLIST))
        raise SystemExit(
            f"Tool {args.tool!r} is not in the approved allowlist.\nAllowed: {allowed}"
        )

    transport = StreamableHttpTransport(
        url=args.mcp_url,
        headers={"Authorization": f"Bearer {token}"},
    )
    client = Client(transport)

    print(f"MCP URL: {args.mcp_url}")
    print(f"Token source: {args.token_env}")

    async with client:
        tools = await client.list_tools()
        tools_by_name = {tool.name: tool for tool in tools}

        if args.list_tools:
            selected_tools = tools
            if args.allowed_only:
                selected_tools = [
                    tool
                    for tool in tools
                    if tool.name in PANDAMON_TOOL_ALLOWLIST
                ]
            for tool in selected_tools:
                print(tool.name)
            return

        if args.tool not in tools_by_name:
            raise SystemExit(f"Tool {args.tool!r} was not found on the server.")

        result = await client.call_tool(args.tool, arguments)
        if result.content:
            for content in result.content:
                text = getattr(content, "text", None)
                print(text if text is not None else content)
        else:
            print(result)


if __name__ == "__main__":
    asyncio.run(main())

