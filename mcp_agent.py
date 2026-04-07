import argparse
import asyncio
import json
import os
import re
import requests
from pathlib import Path
from urllib.parse import urlparse, urlunparse
from fastmcp.client import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport

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

class PanDAAgentOllama:
    def __init__(self, mcp_url:str, ollama_url:str, auth_token:str=None, vo:str=None, transport_mode:str="streamable-http", use_vllm:bool=False, vllm_url:str=None):
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
        self.ollama_url = ollama_url
        self.use_vllm = use_vllm
        self.vllm_url = vllm_url or "http://localhost:8000/v1/completions"
        self.model = "mistral"  # Default model name
        self.conversation_history = []
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

    async def initialize_tools(self):
        """Fetch and store available tools from PanDA MCP"""
        try:
            self.available_tools = await self.client.list_tools()
            return self.available_tools
        except Exception as e:
            print(f"Error fetching tools: {e}")
            return []

    def create_tools_prompt(self):
        """Create a prompt describing available tools for Ollama"""
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

    def is_list_tools_request(self, question: str):
        """Detect explicit requests to print/list available tools."""
        q = question.strip().lower()
        patterns = [
            r"\blist\b.*\btools?\b",
            r"\bprint\b.*\btools?\b",
            r"\bshow\b.*\btools?\b",
            r"\bavailable tools?\b",
            r"\bwhat tools?\b",
            r"\bwhich tools?\b",
        ]
        return any(re.search(pattern, q) for pattern in patterns)

    def parse_tool_call(self, response: str):
        """Parse and validate tool call JSON from an LLM response."""
        if not response:
            return None, None, None

        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None, None, None

        try:
            parsed = json.loads(response[start:end + 1])
        except json.JSONDecodeError:
            return None, None, None

        if not isinstance(parsed, dict):
            return None, None, None

        tool_name = parsed.get("tool")
        arguments = parsed.get("arguments", {})

        if not isinstance(tool_name, str) or not tool_name.strip():
            return None, None, "Invalid tool call format: missing non-empty 'tool' string."
        if not isinstance(arguments, dict):
            return None, None, "Invalid tool call format: 'arguments' must be a JSON object."

        return tool_name.strip(), arguments, None

    async def execute_tool(self, tool_name: str, arguments: dict = None):
        """Execute a PanDA MCP tool"""
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

    def query_ollama(self, prompt: str):
        """Query Ollama server with a prompt and get response"""
        messages = self.conversation_history + [{"role": "user", "content": prompt}]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        
        try:
            response = requests.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            assistant_message = data.get("message", {}).get("content", "")
            return assistant_message
        except Exception as e:
            print(f"Error querying Ollama: {e}")
            return None

    def query_vllm(self, prompt: str, max_tokens: int = 512, temperature: float = 0.7):
        """Query vLLM server with a prompt and get response"""
        payload = {
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        try:
            response = requests.post(self.vllm_url, json=payload)
            response.raise_for_status()
            data = response.json()
            # vLLM returns text in choices[0].text
            return data.get("choices", [{}])[0].get("text", "").strip()
        except Exception as e:
            print(f"Error querying vLLM: {e}")
            return None

    async def process_question(self, question: str):
        """Process a user question using Ollama/vLLM and PanDA tools"""
        if self.is_list_tools_request(question):
            response = self.format_available_tools()
            print(f"Agent: {response}")
            return response

        system_prompt = self.create_tools_prompt()
        full_prompt = f"{system_prompt}\n\nUser question: {question}"
        
        # Choose LLM backend
        if self.use_vllm:
            response = self.query_vllm(full_prompt)
        else:
            response = self.query_ollama(full_prompt)
        
        if not response:
            print("Agent: Failed to get response from LLM.")
            return "Failed to get response from LLM."
        
        # Check if Ollama wants to use a tool
        tool_name, arguments, parse_error = self.parse_tool_call(response)
        if parse_error:
            print(f"Agent: {parse_error}")
            return parse_error

        if tool_name:
            known_tools = {tool.name for tool in self.available_tools}
            if tool_name not in known_tools:
                msg = (
                    f"Tool '{tool_name}' is not available on this MCP server.\n"
                    f"{self.format_available_tools()}"
                )
                print(f"Agent: {msg}")
                return msg

            print(f"Agent: Using tool '{tool_name}'...")
            tool_result = await self.execute_tool(tool_name, arguments)

            if (tool_result and not isinstance(tool_result, dict)) or (
                isinstance(tool_result, dict) and "error" not in tool_result
            ):
                # Send tool result back to Ollama for interpretation
                result_prompt = f"The tool '{tool_name}' returned: {tool_result}. Please interpret this result for the user in a clear, concise way."
                final_response = self.query_ollama(result_prompt)
                print(f"Agent: {final_response}")
                return final_response

            error_msg = f"Failed to execute tool {tool_name}."
            if isinstance(tool_result, dict) and "error" in tool_result:
                error_msg += f" Error: {tool_result['error']}"
            print(f"Agent: {error_msg}")
            return error_msg
        
        print(f"Agent: {response}")
        return response

    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history"""
        self.conversation_history.append({"role": role, "content": content})


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
    
    # Initialize agent
    print("Initializing PanDAAgentOllama...")
    print(f"Server: {args.server if not args.host else 'custom'}")
    print(f"MCP URL: {mcp_url}")
    if args.use_vllm:
        print(f"vLLM URL: {args.vllm_url}")
        print(f"Model: Llama-3.3-70B-Instruct")
    else:
        print(f"Ollama URL: {args.ollama_url}")
        print(f"Model: {args.model}")
    print(f"VO: {args.vo}")
    print(f"Auth: {'✓ Token loaded' if auth_token else '✗ No token'}")
    
    agent = PanDAAgentOllama(
        mcp_url=mcp_url,
        ollama_url=args.ollama_url,
        auth_token=auth_token,
        vo=args.vo,
        use_vllm=args.use_vllm,
        vllm_url=args.vllm_url
    )
    if not args.use_vllm:
        agent.model = args.model
    
    # Connect to PanDA MCP and initialize tools
    try:
        async with agent.client:
            if not agent.client.is_connected():
                print("Failed to connect to PanDA MCP.")
                return
            
            print("Connected to PanDA MCP.")
            await agent.initialize_tools()
            
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
