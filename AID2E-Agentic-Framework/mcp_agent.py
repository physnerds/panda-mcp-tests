import argparse
import asyncio
import json
import os
from pathlib import Path
from agent.BaseAgent import BaseAgent
from agent.llm_providers import LLMProvider, llm_provider
from agent.PanDASWFAgent import DEFAULT_SWF_MCP_URL, PanDASWFAgent

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

class PanDAAgentNative(BaseAgent):
    """PanDA MCP agent backed by Ollama or vLLM."""

    def __init__(
        self,
        mcp_url: str,
        ollama_url: str = "http://localhost:11434",
        llm: LLMProvider = None,
        auth_token: str = None,
        vo: str = None,
        transport_mode: str = "streamable-http",
        use_vllm: bool = False,
        vllm_url: str = None,
        model: str = "mistral",
    ):
        super().__init__(
            mcp_url=mcp_url,
            ollama_url=ollama_url,
            llm=llm,
            auth_token=auth_token,
            vo=vo,
            transport_mode=transport_mode,
            use_vllm=use_vllm,
            vllm_url=vllm_url,
            model=model,
            agent_name="PanDAAgentNative",
        )


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="PanDA MCP Agent with Ollama or vLLM")
    parser.add_argument(
        "--agent",
        type=str,
        choices=["native", "swf"],
        default="native",
        help="Agent to run: 'native' for PanDA MCP or 'swf' for PanDA-SWF MCP (default: native)",
    )
    parser.add_argument(
        "--server",
        type=str,
        choices=["docker", "sdcc"],
        default="docker",
        help="PanDA MCP server to connect to for --agent native: 'docker' for localhost:25888 or 'sdcc' for pandaserver01.sdcc.bnl.gov:25443 (default: docker)",
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
        "--use_gpt_oss",
        action="store_true",
        help="Use local Ollama gpt-oss:20b instead of the --model value (default: False)",
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
    parser.add_argument(
        "--swf_url",
        type=str,
        default=DEFAULT_SWF_MCP_URL,
        help=f"PanDA-SWF MCP URL (default: {DEFAULT_SWF_MCP_URL})",
    )
    
    args = parser.parse_args()
    
    auth_token = None
    if args.agent == "swf":
        mcp_url = args.swf_url
    else:
        # Determine native PanDA MCP server configuration
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
    
    llm = llm_provider(
        use_vllm=args.use_vllm,
        use_gpt_oss=args.use_gpt_oss,
        ollama_url=args.ollama_url,
        ollama_model=args.model,
        vllm_url=args.vllm_url,
    )
    llm_info = llm.info()

    agent_label = "PanDA-SWF Agent" if args.agent == "swf" else "PanDAAgentNative"

    # Initialize agent
    print(f"Initializing {agent_label}...")
    if args.agent == "native":
        print(f"Server: {args.server if not args.host else 'custom'}")
    print(f"MCP URL: {mcp_url}")
    print(f"LLM Provider: {llm_info['provider']}")
    print(f"LLM URL: {llm_info['url']}")
    print(f"Model: {llm_info['model']}")
    if args.agent == "native":
        print(f"VO: {args.vo}")
        print(f"Auth: {'✓ Token loaded' if auth_token else '✗ No token'}")
    else:
        print("SWF Auth: requires SSL_CERT_DIR and SWF_MONITOR_TOKEN in the environment")

    if args.agent == "swf":
        agent = PanDASWFAgent(
            mcp_url=mcp_url,
            llm=llm,
        )
    else:
        agent = PanDAAgentNative(
            mcp_url=mcp_url,
            llm=llm,
            auth_token=auth_token,
            vo=args.vo,
        )
    
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
            print(f"{agent_label} Ready! Ask questions about PanDA.")
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
