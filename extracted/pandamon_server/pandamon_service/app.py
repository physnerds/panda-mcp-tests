import os

from mcp.server.fastmcp import FastMCP

MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "swf-pandamon-mcp")
MCP_SERVER_INSTRUCTIONS = os.getenv(
    "MCP_SERVER_INSTRUCTIONS",
    "Read-only PanDA Monitor MCP tools for ePIC production monitoring.",
)

mcp = FastMCP(
    MCP_SERVER_NAME,
    instructions=MCP_SERVER_INSTRUCTIONS,
    stateless_http=True,
    json_response=True,
    streamable_http_path="/mcp",
)
