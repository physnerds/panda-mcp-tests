import os

from mcp.server.fastmcp import FastMCP

MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "aid2e-mcp")
MCP_SERVER_INSTRUCTIONS = os.getenv(
    "MCP_SERVER_INSTRUCTIONS",
    "MCP tools for running the AID2E command line interface.",
)

mcp = FastMCP(
    MCP_SERVER_NAME,
    instructions=MCP_SERVER_INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
)
