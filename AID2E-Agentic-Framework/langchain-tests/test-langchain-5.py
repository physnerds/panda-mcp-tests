import asyncio
import json
import os
import ssl
from datetime import datetime, timezone
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
# Needed for the response schema
from pydantic import BaseModel, Field

DEFAULT_SWF_MCP_URL = "https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/"
DEFAULT_OPENVIKING_MCP_URL = "http://localhost:25901/mcp/"
DEFAULT_SDDC_CERT_DIR = (
    Path(__file__).resolve().parents[2] / "sdcc-grid-certificates"
)


#  A response schema to be used by the model to output the answer
class ResponseSchema(BaseModel):
    final_output: str = Field(
    description = "Final output that answers the user's prompt")
    tool_used: list[str] = Field(
        description = "List of tools used to obtain the final output"
    )
    input_token: int = Field(
        description = "Number of input tokens used"
    )
    output_token: int = Field(
        description = "Number of output tokens used"
    )

# Convert the output of the Langchain result into the above schema:

def create_response_schema(result:dict) -> ResponseSchema:
    messages = result.get("messages", [])

    final_output = ""
    tool_used = []
    input_tokens = 0
    output_tokens = 0

    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        content = message.content
        usage = message.usage_metadata or {}
        input_tokens += int(usage.get("input_tokens", 0))
        output_tokens += int(usage.get("output_tokens", 0))
        for tool_call in message.tool_calls:
            tool_name = tool_call.get("name")
            if tool_name and tool_name not in tool_used:
                tool_used.append(tool_name)
        
        if isinstance(content, str):
            final_output = content
        else:
            final_output = str(content)
        input_tokens += message.input_tokens if hasattr(message, "input_tokens") else 0
        output_tokens += message.output_tokens if hasattr(message, "output_tokens") else 0
    return ResponseSchema(
        final_output=final_output,
        tool_used=tool_used,
        input_token=input_tokens,
        output_token=output_tokens
    )



async def build_panda_agent(
    model="nemotron-3-ultra-550b-nvfp4",
    base_url=None,
    api_key=None,
    swf_token=None,
    swf_mcp_url=DEFAULT_SWF_MCP_URL,
):
    base_url = base_url or os.environ["BNL_BASE_URL"]
    api_key = api_key or os.environ["BNL_API_KEY"]
    swf_token = swf_token or os.environ["SWF_MONITOR_MCP_TOKEN"]
    model = ChatOpenAI(model = model,
                       base_url = base_url,
                       api_key = api_key
                       )
    transport = StreamableHttpTransport(
        swf_mcp_url,
        headers={"Authorization": f"Bearer {swf_token}"},
    )
    client = Client(transport)
    adapter = MCPAdapter(client)
    tools = await adapter.list_tools()

    agent =  create_agent(model = model,
                        tools = tools,
                        system_prompt=(
                            "You are a PanDA job-monitoring agent. Use the available tools to "
                            "inspect the jobs and return relevant information. Never make assumptions. Do not submit, retry or cancel work without approval."
                        ),
                        #response_format = ToolStrategy(ResponseSchema),
                        name = "panda-monitor",
    )
    return agent, tools

async def ask_panda(agent, question: str) -> ResponseSchema:
    result = await agent.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    })
    return create_response_schema(result)


async def build_openviking_agent(
    model="nemotron-3-ultra-550b-nvfp4",
    base_url=None,
    api_key=None,
    mcp_url=None,
    mcp_token=None,
):
    """Build a LangChain agent backed by the OpenViking MCP knowledge tools.

    ``OPENVIKING_URL`` and ``OPENVIKING_API_KEY_FILE`` belong to the MCP
    server's connection to the OpenViking backend.  This client connects to
    the MCP endpoint through ``OPENVIKING_MCP_URL`` and only sends a bearer
    token when that endpoint is independently protected.
    """
    base_url = base_url or os.environ["BNL_BASE_URL"]
    api_key = api_key or os.environ["BNL_API_KEY"]
    chat_model = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )

    mcp_url = mcp_url or os.environ.get(
        "OPENVIKING_MCP_URL", DEFAULT_OPENVIKING_MCP_URL
    )
    mcp_token = mcp_token or os.environ.get("OPENVIKING_MCP_TOKEN")
    headers = {"Authorization": f"Bearer {mcp_token}"} if mcp_token else None
    transport = StreamableHttpTransport(mcp_url, headers=headers)
    client = Client(transport)
    adapter = MCPAdapter(client)
    tools = await adapter.list_tools()

    agent = create_agent(
        model=chat_model,
        tools=tools,
        system_prompt=(
            "You are an OpenViking knowledge-retrieval agent. Use openviking_find "
            "for semantic discovery when the exact viking:// URI is unknown, or "
            "openviking_ls to inspect resource directories. Ground substantive "
            "answers by calling openviking_read on the exact resource URI; use "
            "openviking_abstract for quick L0 orientation and openviking_overview "
            "for an L1 summary. Preserve and cite viking:// resource URIs in the "
            "answer, distinguish retrieved evidence from inference, and state when "
            "no supporting resource was found. Treat results with ok=false or "
            "isError=true as failures. Call openviking_add_resource only when the "
            "user explicitly asks to ingest a known, sanitized local path; never "
            "ingest credentials, tokens, keys, certificates, or sensitive logs."
        ),
        name="openviking-knowledge",
    )
    return agent, tools


async def ask_openviking(agent, question: str) -> ResponseSchema:
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": question}]}
    )
    return create_response_schema(result)


def write_panda_observation(
    question: str,
    response: ResponseSchema,
    observation_dir: str | None = None,
) -> Path:
    """Write a compact, sanitized PanDA observation for OpenViking ingestion."""
    recorded_at = datetime.now(timezone.utc)
    output_dir = Path(
        observation_dir
        or os.environ.get(
            "OPENVIKING_OBSERVATION_DIR", "/tmp/openviking-panda-evidence"
        )
    ).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / recorded_at.strftime(
        "panda-observation-%Y%m%dT%H%M%S%fZ.json"
    )
    observation = {
        "schema_version": 1,
        "recorded_at": recorded_at.isoformat(),
        "source": {
            "agent": "panda-monitor",
            "mcp_server": DEFAULT_SWF_MCP_URL,
        },
        "question": question,
        "response": response.model_dump(),
    }
    output_path.write_text(
        json.dumps(observation, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path.resolve()




async def main():
    question = (
        "What is the status of the PanDA job 958688? Give me a one sentence answer."
    )
    panda_agent, _ = await build_panda_agent()
    openviking_agent, _ = await build_openviking_agent()

    panda_response = await ask_panda(panda_agent, question)
    observation_path = write_panda_observation(question, panda_response)

    # openviking_add_resource reads a path on the MCP server host. The default
    # works for a local MCP wrapper; use OPENVIKING_OBSERVATION_DIR on a shared
    # filesystem when the wrapper runs remotely.
    ingestion_response = await ask_openviking(
        openviking_agent,
        (
            "The user explicitly authorizes storing this sanitized PanDA "
            "monitoring observation in OpenViking. Call openviking_add_resource "
            "exactly once with "
            f"path={json.dumps(str(observation_path))}, wait=false, and no other "
            "optional arguments. Report whether ingestion was accepted and include "
            "the returned OpenViking resource URI or task/ingestion identifier. "
            "Do not claim indexing is complete when the result only confirms that "
            "the asynchronous ingestion was accepted."
        ),
    )

    print("PanDA response:")
    print(panda_response.model_dump_json(indent=2))
    print(f"Observation file: {observation_path}")
    print("OpenViking ingestion response:")
    print(ingestion_response.model_dump_json(indent=2))

if __name__ == "__main__":
    asyncio.run(main())
