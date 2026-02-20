import argparse
import asyncio
import json
import requests
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport   

'''
This is an implementation of an agent that connects to PanDA MCP server
and an Ollama server to answer questions using available PanDA tools.
'''
class PanDAAgentOllama:
    def __init__(self, mcp_url:str, ollama_url:str, auth_token:str=None, vo:str=None):
        headers = {"Origin": vo} if vo and auth_token else None
        self.transport = StreamableHttpTransport(url=mcp_url, auth=auth_token, headers=headers)
        self.client = Client(transport=self.transport)
        self.ollama_url = ollama_url
        self.model = "mistral"
        self.conversation_history = []
        self.available_tools = []

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
            
            # Check if tool requires arguments
            schema = tool.inputSchema
            has_args = schema.get('properties', {}) if isinstance(schema, dict) else False
            
            tools_description += f"- {tool.name}: {short_desc}"
            if not has_args:
                tools_description += " (no arguments required)"
            tools_description += "\n"
        
        tools_description += "\nWhen you need to use a tool, respond with JSON in this exact format: {\"tool\": \"tool_name\", \"arguments\": {}}."
        tools_description += "\nFor tools that require no arguments, use an empty arguments object: {\"arguments\": {}}."
        return tools_description

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

    async def process_question(self, question: str):
        """Process a user question using Ollama and PanDA tools"""
        # Create system prompt with available tools
        system_prompt = self.create_tools_prompt()
        full_prompt = f"{system_prompt}\n\nUser question: {question}"
        
        # Query Ollama
        response = self.query_ollama(full_prompt)
        
        if not response:
            print("Agent: Failed to get response from Ollama.")
            return "Failed to get response from Ollama."
        
        # Check if Ollama wants to use a tool
        try:
            # Try to parse as JSON for tool call
            if "{" in response and "tool" in response:
                tool_call = json.loads(response[response.find("{"):response.rfind("}")+1])
                tool_name = tool_call.get("tool")
                arguments = tool_call.get("arguments", {})
                
                print(f"Agent: Using tool '{tool_name}'...")
                tool_result = await self.execute_tool(tool_name, arguments)
                
                if tool_result and not isinstance(tool_result, dict) or (isinstance(tool_result, dict) and "error" not in tool_result):
                    # Send tool result back to Ollama for interpretation
                    result_prompt = f"The tool '{tool_name}' returned: {tool_result}. Please interpret this result for the user in a clear, concise way."
                    final_response = self.query_ollama(result_prompt)
                    print(f"Agent: {final_response}")
                    return final_response
                else:
                    error_msg = f"Failed to execute tool {tool_name}."
                    if isinstance(tool_result, dict) and "error" in tool_result:
                        error_msg += f" Error: {tool_result['error']}"
                    print(f"Agent: {error_msg}")
                    return error_msg
        except json.JSONDecodeError:
            # Not a tool call, just a regular response
            print(f"Agent: {response}")
            return response
        
        print(f"Agent: {response}")
        return response

    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history"""
        self.conversation_history.append({"role": role, "content": content})


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="PanDA MCP Agent with Ollama")
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
        help="OIDC ID token for write-operations (default: None)",
    )
    parser.add_argument(
        "--vo",
        type=str,
        default=None,
        help="Virtual organization with ID token (default: None)",
    )
    
    args = parser.parse_args()
    
    # Determine server configuration
    if args.host and args.port:
        # Custom host and port provided
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
    
    # Construct MCP URL
    protocol = "http" if use_http else "https"
    mcp_url = f"{protocol}://{mcp_host}:{mcp_port}/mcp/"
    
    # Initialize agent
    print("Initializing PanDAAgentOllama...")
    print(f"Server: {args.server if not args.host else 'custom'}")
    print(f"MCP URL: {mcp_url}")
    print(f"Ollama URL: {args.ollama_url}")
    print(f"Model: {args.model}")
    
    agent = PanDAAgentOllama(
        mcp_url=mcp_url,
        ollama_url=args.ollama_url,
        auth_token=args.token,
        vo=args.vo
    )
    agent.model = args.model
    print("PanDAAgentOllama initialized.")

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