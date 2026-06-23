#!/usr/bin/env python3
"""Standalone AID2E agent for the deployed SWF Testbed PanDAMon MCP server."""

import argparse
import asyncio
import os
from typing import Any, Dict, List

from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

from base_agent import BaseAgent
from llm_providers import OllamaProvider, VLLMProvider


DEFAULT_MCP_URL = "https://pandaserver02.sdcc.bnl.gov/swf-monitor/mcp/"
DEFAULT_TOKEN_ENV = "SWF_MONITOR_MCP_TOKEN"

PANDAMON_TOOL_ALLOWLIST = frozenset(
    {
        "panda_get_activity",
        "panda_list_jobs",
        "panda_diagnose_jobs",
        "panda_list_tasks",
        "panda_error_summary",
        "panda_study_job",
        "panda_list_queues",
        "panda_get_queue",
        "panda_resource_usage",
        "panda_harvester_workers",
    }
)


class SWFTestbedPanDAMonAgent(BaseAgent):
    """LLM-driven client restricted to approved PanDAMon tools."""

    def __init__(self, mcp_url: str, token: str, llm_provider):
        super().__init__(llm_provider, agent_name="SWFTestbedPanDAMonAgent")
        self.mcp_url = mcp_url
        self.transport = StreamableHttpTransport(
            url=mcp_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.client = Client(transport=self.transport)
        self.available_tools: List[Any] = []

    async def initialize(self) -> bool:
        """Discover tools and retain only the exact approved tool set."""
        try:
            discovered_tools = await self.client.list_tools()
            self.available_tools = [
                tool
                for tool in discovered_tools
                if tool.name in PANDAMON_TOOL_ALLOWLIST
            ]
            return True
        except Exception as exc:
            print(f"Error fetching SWF testbed tools: {exc}")
            return False

    def get_available_tools(self) -> List[Any]:
        return self.available_tools

    def format_available_tools(self) -> str:
        if not self.available_tools:
            return "No approved PanDAMon tools are currently available."

        lines = [f"Available PanDAMon tools ({len(self.available_tools)}):"]
        for tool in self.available_tools:
            description = (tool.description or "").strip().splitlines()
            summary = description[0] if description else ""
            lines.append(f"- {tool.name}: {summary}")
        return "\n".join(lines)

    def create_system_prompt(self) -> str:
        lines = [
            "You are an AID2E assistant for read-only PanDA monitoring.",
            "Use only the following approved PanDAMon tools:",
            "",
        ]

        for tool in self.available_tools:
            description = (tool.description or "").strip().splitlines()
            summary = description[0] if description else ""
            schema = tool.inputSchema if isinstance(tool.inputSchema, dict) else {}
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))
            parameters = []
            for name, definition in properties.items():
                parameter_type = definition.get("type", "any")
                marker = ", required" if name in required else ""
                parameters.append(f"{name} ({parameter_type}{marker})")

            line = f"- {tool.name}: {summary}"
            if parameters:
                line += f" Parameters: {', '.join(parameters)}"
            lines.append(line)

        lines.extend(
            [
                "",
                "To call a tool, respond with exactly one JSON object:",
                '{"tool": "tool_name", "arguments": {"parameter": "value"}}',
                "Use exact tool and parameter names. Use an empty arguments object "
                "for tools with no parameters.",
            ]
        )
        return "\n".join(lines)

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Call an approved and currently discovered tool."""
        if tool_name not in PANDAMON_TOOL_ALLOWLIST:
            return {"error": f"Tool '{tool_name}' is not allowed by this client."}

        available_names = {tool.name for tool in self.available_tools}
        if tool_name not in available_names:
            return {"error": f"Tool '{tool_name}' was not discovered on the server."}

        try:
            return await self.client.call_tool(tool_name, arguments or {})
        except Exception as exc:
            return {"error": str(exc)}


def parse_args():
    parser = argparse.ArgumentParser(
        description="AID2E agent for the deployed SWF Testbed PanDAMon MCP server"
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
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama server URL",
    )
    parser.add_argument("--model", default="mistral", help="Ollama model")
    parser.add_argument("--use-vllm", action="store_true", help="Use vLLM")
    parser.add_argument(
        "--vllm-url",
        default="http://localhost:8000/v1/completions",
        help="vLLM completions URL",
    )
    parser.add_argument(
        "--vllm-model",
        default="meta-llama/Llama-3.3-70B-Instruct",
        help="vLLM model identifier",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    token = os.getenv(args.token_env)
    if not token:
        raise SystemExit(
            f"Missing bearer token. Set environment variable {args.token_env}."
        )

    if args.use_vllm:
        llm_provider = VLLMProvider(
            base_url=args.vllm_url,
            model=args.vllm_model,
        )
    else:
        llm_provider = OllamaProvider(
            base_url=args.ollama_url,
            model=args.model,
        )

    agent = SWFTestbedPanDAMonAgent(
        mcp_url=args.mcp_url,
        token=token,
        llm_provider=llm_provider,
    )

    print(f"MCP URL: {args.mcp_url}")
    print(f"LLM provider: {llm_provider.get_provider_name()}")
    print(f"Token source: {args.token_env}")

    try:
        async with agent.client:
            if not agent.client.is_connected():
                print("Failed to connect to the SWF testbed MCP server.")
                return

            if not await agent.initialize():
                return

            print(agent.format_available_tools())
            print("\nAgent ready. Type 'exit' to quit.")

            while True:
                try:
                    question = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break

                if question.lower() in {"exit", "quit", "q"}:
                    break
                if question:
                    await agent.process_question(question)
                    print()
    except Exception as exc:
        print(f"Connection error: {exc}")


if __name__ == "__main__":
    asyncio.run(main())

