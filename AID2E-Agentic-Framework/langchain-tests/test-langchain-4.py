import os,asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
# Needed for the response schema
from pydantic import BaseModel, Field
from langchain.agents.structured_output import ToolStrategy

DEFAULT_SWF_MCP_URL = "https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/"


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

async def build_panda_agent( model = "nemotron-3-ultra-550b-nvfp4", base_url = os.environ["BNL_BASE_URL"], api_key = os.environ["BNL_API_KEY"],swf_token = os.environ["SWF_MONITOR_MCP_TOKEN"]):
    model = ChatOpenAI(model = model,
                       base_url = base_url,
                       api_key = api_key
                       )
    transport = StreamableHttpTransport(DEFAULT_SWF_MCP_URL, 
                                        headers = {"Authorization": f"Bearer {swf_token}"})
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
    import json
    result = await agent.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    })
    return create_response_schema(result)


async def main():
    agent, tools = await build_panda_agent()
    response = await ask_panda(agent, "What is the status of the PanDA job 958688? Give me a one sentence answer.")
    print(response.model_dump_json(indent=2))

if __name__ == "__main__":
    asyncio.run(main())