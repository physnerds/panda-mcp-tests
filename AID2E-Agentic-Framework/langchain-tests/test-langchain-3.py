import os,asyncio
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport

DEFAULT_SWF_MCP_URL = "https://pandaserver02.sdcc.bnl.gov:8443/swf-monitor/mcp/"

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
                            " For each response, include tool_used, input_token, and output_token usage. Do not invent these values."
                        ),
                        name = "panda-monitor",
    )
    return agent

async def ask_panda(agent, question: str) -> str:
    import json
    result = await agent.ainvoke({
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ]
    })
    for key in result:
        print(key, ":", result[key])
    final_message = result["messages"][-1]
    content = final_message.content
    # openai compatible response
    if isinstance(content, str):
        return content
    # What if the response is a list or structured content blocks
    if isinstance(content, list):
        return "\n".join(str(item) for item in content)
    return str(content)


async def main():
    agent = await build_panda_agent()
    response = await ask_panda(agent, "What is the status of the PanDA job 958688? Summarize it's status")
    print(response)

if __name__ == "__main__":
    asyncio.run(main())