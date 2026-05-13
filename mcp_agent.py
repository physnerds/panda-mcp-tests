import argparse
import asyncio
import json
import os
import re
import requests
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse, urlunparse
from fastmcp.client import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport
from llm_providers import LLMProvider, OllamaProvider, VLLMProvider
from base_agent import BaseAgent

def load_token_from_file(token_file=".token"):
    """Load OIDC ID token from .token file"""
    try:
        token_path = Path(token_file)
        if not token_path.exists():
            return None
        
        with open(token_path, 'r') as f:
            token_data = json.load(f)
            return token_data.get('id_token')
    except Exception as e:
        print(f"Warning: Failed to load token from {token_file}: {e}")
        return None

class PanDAMCPAgent(BaseAgent):
    """
    PanDA MCP Agent - specialized agent for interacting with PanDA WMS via MCP protocol.
    
    This agent connects to a PanDA MCP server, discovers available tools,
    and uses an LLM to interpret user questions and execute appropriate PanDA operations.
    """
    
    def __init__(self, mcp_url: str, llm_provider: LLMProvider, auth_token: str = None, vo: str = None, transport_mode: str = "streamable-http"):
        """Initialize PanDA MCP Agent.
        
        Args:
            mcp_url: PanDA MCP server URL
            llm_provider: LLM provider instance (OllamaProvider, VLLMProvider, etc.)
            auth_token: OIDC authentication token
            vo: Virtual organization
            transport_mode: MCP transport type ("sse" or "streamable-http")
        """
        super().__init__(llm_provider, agent_name="PanDAMCPAgent")
        
        self.mcp_url = mcp_url
        self.auth_token = auth_token
        self.vo = vo
        
        # Build headers with OIDC token in PanDA-expected format
        self.headers = {}
        if auth_token:
            self.headers['Authorization'] = f'Bearer {auth_token}'
            self.headers['X-PANDAAUTH-TOKEN'] = auth_token
        if vo:
            self.headers['Origin'] = vo
        
        self.transport = self._build_transport(mcp_url, transport_mode)
        self.client = Client(transport=self.transport)
        self.transport_mode = transport_mode
        self.available_tools = []

    def _build_transport(self, mcp_url: str, transport_mode: str):
        """Build transport with proper authentication headers"""
        # Pass headers to transport - FastMCP will include them in all requests
        if transport_mode == "sse":
            return SSETransport(
                url=mcp_url, 
                headers=self.headers if self.headers else None
            )
        
        return StreamableHttpTransport(
            url=mcp_url, 
            headers=self.headers if self.headers else None
        )

    async def initialize(self) -> bool:
        """Fetch and store available tools from PanDA MCP."""
        try:
            self.available_tools = await self.client.list_tools()
            return True
        except Exception as e:
            print(f"Error fetching tools: {e}")
            return False
    
    def get_available_tools(self) -> List[Any]:
        """Return list of available MCP tools."""
        return self.available_tools

    def create_system_prompt(self) -> str:
        """Create a system prompt describing available PanDA tools for the LLM."""
        tools_description = "You have access to the following PanDA tools:\n\n"
        for tool in self.available_tools:
            # Extract just the tool name and first line of description
            desc_lines = tool.description.strip().split('\n')
            short_desc = desc_lines[0] if desc_lines else ""
            
            # Get schema information
            schema = tool.inputSchema
            params_info = ""
            if schema and isinstance(schema, dict):
                properties = schema.get('properties', {})
                required = schema.get('required', [])
                
                if properties:
                    param_details = []
                    for param_name, param_schema in properties.items():
                        param_type = param_schema.get('type', 'any')
                        param_desc = param_schema.get('description', '')
                        is_required = param_name in required
                        
                        detail = f"'{param_name}' ({param_type}"
                        if is_required:
                            detail += ", required"
                        detail += ")"
                        if param_desc:
                            detail += f": {param_desc}"
                        param_details.append(detail)
                    
                    params_info = f" - Parameters: {', '.join(param_details)}"
            
            tools_description += f"- {tool.name}: {short_desc}{params_info}\n"
        
        tools_description += "\nWhen you need to use a tool, respond with JSON in this exact format: {\"tool\": \"tool_name\", \"arguments\": {\"param_name\": value}}."
        tools_description += "\nUse the EXACT parameter names shown above. For example, if a tool uses 'job_ids', do not use 'jobId'."
        tools_description += "\nFor tools that require no arguments, use an empty arguments object: {\"arguments\": {}}."
        tools_description += "\nIf the user asks to list available tools, answer directly in plain text and do not emit a tool call JSON."
        return tools_description

    def format_available_tools(self):
        """Render available tools as human-readable text."""
        if not self.available_tools:
            return "No tools are currently available from the connected MCP server."

        lines = [f"Available tools ({len(self.available_tools)}):"]
        for tool in self.available_tools:
            desc = (tool.description or "").strip().split("\n")[0]
            line = f"- {tool.name}"
            if desc:
                line += f": {desc}"
            lines.append(line)
        return "\n".join(lines)



    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a PanDA MCP tool."""
        try:
            # Find the tool to check its schema
            tool_schema = None
            for tool in self.available_tools:
                if tool.name == tool_name:
                    tool_schema = tool.inputSchema
                    break
            
            # If tool has no properties in schema, pass empty dict
            if tool_schema and isinstance(tool_schema, dict):
                required_props = tool_schema.get('properties', {})
                if not required_props:
                    # Tool takes no arguments
                    arguments = {}
            
            if arguments is None:
                arguments = {}
            
            result = await self.client.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            print(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="PanDA MCP Agent with Ollama or vLLM")
    parser.add_argument(
        "--server",
        type=str,
        choices=["docker", "sdcc"],
        default="docker",
        help="PanDA MCP server to connect to: 'docker' for localhost:25888 or 'sdcc' for pandaserver01.sdcc.bnl.gov:25443 (default: docker)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Custom PanDA MCP server host (overrides --server option)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Custom PanDA MCP server port (overrides --server option)",
    )
    parser.add_argument(
        "--use_http",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Use HTTP instead of HTTPS (default: auto-detected based on --server)",
    )
    parser.add_argument(
        "--ollama_url",
        type=str,
        default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="mistral",
        help="Ollama model to use (default: mistral)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="OIDC ID token for authentication (default: auto-load from .token file)",
    )
    parser.add_argument(
        "--token_file",
        type=str,
        default=".token",
        help="Path to token file (default: .token)",
    )
    parser.add_argument(
        "--vo",
        type=str,
        default=os.getenv("PANDA_AUTH_VO", "EIC"),
        help="Virtual organization (default: EIC or PANDA_AUTH_VO env var)",
    )
    parser.add_argument(
        "--use_vllm",
        action="store_true",
        help="Use vLLM instead of Ollama (default: False)",
    )
    parser.add_argument(
        "--vllm_url",
        type=str,
        default="http://localhost:8000/v1/completions",
        help="vLLM server URL (default: http://localhost:8000/v1/completions)",
    )
    
    args = parser.parse_args()
    
    # Determine server configuration
    if args.host and args.port:
        mcp_host = args.host
        mcp_port = args.port
        use_http = args.use_http if args.use_http is not None else False
    elif args.server == "docker":
        mcp_host = "localhost"
        mcp_port = 25888
        use_http = args.use_http if args.use_http is not None else True
    else:  # sdcc
        mcp_host = "pandaserver01.sdcc.bnl.gov"
        mcp_port = 25443
        use_http = args.use_http if args.use_http is not None else False
    
    # Load token from file if not provided via CLI
    auth_token = args.token
    if not auth_token:
        auth_token = load_token_from_file(args.token_file)
        if auth_token:
            print(f"✓ Loaded auth token from {args.token_file}")
        else:
            print(f"⚠ No auth token found. Some operations may be restricted.")
    
    # Construct MCP URL
    protocol = "http" if use_http else "https"
    mcp_url = f"{protocol}://{mcp_host}:{mcp_port}/mcp/"
    
    # Create LLM provider
    if args.use_vllm:
        llm_provider = VLLMProvider(
            base_url=args.vllm_url,
            model="meta-llama/Llama-3.3-70B-Instruct"
        )
    else:
        llm_provider = OllamaProvider(
            base_url=args.ollama_url,
            model=args.model
        )
    
    # Initialize agent
    print("Initializing PanDA Agent...")
    print(f"Server: {args.server if not args.host else 'custom'}")
    print(f"MCP URL: {mcp_url}")
    print(f"LLM Provider: {llm_provider.get_provider_name()}")
    print(f"VO: {args.vo}")
    print(f"Auth: {'✓ Token loaded' if auth_token else '✗ No token'}")
    
    agent = PanDAMCPAgent(
        mcp_url=mcp_url,
        llm_provider=llm_provider,
        auth_token=auth_token,
        vo=args.vo
    )
    
    # Connect to PanDA MCP and initialize tools
    try:
        async with agent.client:
            if not agent.client.is_connected():
                print("Failed to connect to PanDA MCP.")
                return
            
            print("Connected to PanDA MCP.")
            initialized = await agent.initialize()
            if not initialized:
                print("Failed to initialize agent tools.")
                return
            
            print(f"\nAvailable tools: {len(agent.available_tools)}")
            for tool in agent.available_tools:
                print(f"- {tool.name}")
            
            # Interactive loop
            print("\n" + "="*50)
            print("PanDA Agent Ready! Ask questions about PanDA.")
            print("Type 'exit' to quit.")
            print("="*50 + "\n")
            
            while True:
                try:
                    question = input("You: ").strip()
                    if question.lower() in ['exit', 'quit', 'q']:
                        print("Goodbye!")
                        break
                    
                    if not question:
                        continue
                    
                    await agent.process_question(question)
                    print()  # Add blank line for readability
                    
                except KeyboardInterrupt:
                    print("\nGoodbye!")
                    break
                except Exception as e:
                    print(f"Error: {e}")
    except Exception as e:
        print(f"Connection error: {e}")
        print("\nTroubleshooting tips:")
        print("- For Docker: Ensure the container is running with 'sudo docker ps | grep panda-mcp'")
        print("- For SDCC: Check network connectivity to pandaserver01.sdcc.bnl.gov")
        print("- Verify the MCP service is running inside the container/server")


if __name__ == "__main__":
    asyncio.run(main())
