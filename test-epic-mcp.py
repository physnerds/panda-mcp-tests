#!/usr/bin/env python3

import asyncio
import os
import json
import inspect

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

'''
Test designed for the sdcc machines.
SSL_CERT_DIR is set to /etc/grid-security/certificates/
SWF_MONITOR_MCP_TOKEN is expected to have the token value
'''

URL = "https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/"


def pretty(obj):
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(), indent=2, default=str)
    return json.dumps(obj, indent=2, default=str)


async def main():
    token = os.environ.get("SWF_MONITOR_MCP_TOKEN")
    if not token:
        raise RuntimeError("SWF_MONITOR_MCP_TOKEN environment "
                           "variable is not set")

    async with streamablehttp_client(
        url=URL,
        headers={"Authorization": f"Bearer {token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            print("\nInitializing MCP session...")
            await session.initialize()
            print("Initialized.")

            tools_result = await session.list_tools()
            tools = tools_result.tools

            print("\n=========== panda_* tools ===========")
            for tool in tools:
                if tool.name.startswith("panda_"):
                    print(f"\nTool: {tool.name}")
                    print(f"Description: {tool.description}")
                    print("Input schema:")
                    print(pretty(getattr(tool, "inputSchema", {})))

            target_tool = "panda_get_activity"

            if not any(tool.name == target_tool for tool in tools):
                print(f"\n{target_tool} not found.")
                return

            print(f"\nCalling {target_tool}...")
            result = await session.call_tool(target_tool, {})
            print("\n=========== Result ===========")
            print(pretty(result))


if __name__ == "__main__":
    asyncio.run(main())