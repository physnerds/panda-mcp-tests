import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastmcp.client import Client
from fastmcp.client.transports import SSETransport, StreamableHttpTransport

from agent.llm_providers import LLMProvider, llm_provider


class BaseAgent:
    """Common MCP client, LLM query, tool discovery, and tool execution flow."""

    def __init__(
        self,
        mcp_url: str,
        ollama_url: str = "http://localhost:11434",
        llm: Optional[LLMProvider] = None,
        auth_token: Optional[str] = None,
        vo: Optional[str] = None,
        transport_mode: str = "streamable-http",
        use_vllm: bool = False,
        vllm_url: Optional[str] = None,
        model: str = "mistral",
        vllm_model: str = "meta-llama/Llama-3.3-70B-Instruct",
        agent_name: Optional[str] = None,
    ):
        self.agent_name = agent_name or self.__class__.__name__
        self.mcp_url = mcp_url
        self.auth_token = auth_token
        self.vo = vo
        self.transport_mode = transport_mode

        self.headers = self._build_headers(auth_token, vo)
        self.transport = self._build_transport(mcp_url, transport_mode)
        self.client = self._create_client()

        self.llm = llm or llm_provider(
            use_vllm=use_vllm,
            ollama_url=ollama_url,
            ollama_model=model,
            vllm_url=vllm_url or "http://localhost:8000/v1/completions",
            vllm_model=vllm_model,
        )

        self.conversation_history: List[Dict[str, str]] = []
        self.available_tools: List[Any] = []
        self._last_llm_prompt: Optional[str] = None
        self._last_llm_response: Optional[str] = None

    def _build_headers(
        self, auth_token: Optional[str], vo: Optional[str]
    ) -> Dict[str, str]:
        """Build authentication and VO headers for MCP transports."""
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
            headers["X-PANDAAUTH-TOKEN"] = auth_token
        if vo:
            headers["Origin"] = vo
        return headers

    def _build_transport(self, mcp_url: str, transport_mode: str):
        """Build the configured FastMCP transport."""
        headers = self.headers if self.headers else None
        if transport_mode == "sse":
            return SSETransport(url=mcp_url, headers=headers)
        return StreamableHttpTransport(url=mcp_url, headers=headers)

    def _create_client(self) -> Client:
        """Create a FastMCP client from the configured transport."""
        return Client(transport=self.transport)

    async def initialize(self) -> bool:
        """Initialize agent resources and discover MCP tools."""
        tools = await self.initialize_tools()
        return bool(tools)

    async def initialize_tools(self):
        """Fetch and store available tools from the configured MCP server."""
        try:
            self.available_tools = await self.client.list_tools()
            return self.available_tools
        except Exception as e:
            print(f"Error fetching tools: {e}")
            self.available_tools = []
            return []

    def get_available_tools(self):
        """Return the currently discovered tools."""
        return self.available_tools

    def get_llm_info(self) -> Dict[str, str]:
        """Return information about the configured LLM backend."""
        return self.llm.info()

    def create_tools_prompt(self) -> str:
        """Create an LLM prompt from tool_description.md and discovered tools."""
        template_path = Path(__file__).with_name("tool_description.md")
        template = template_path.read_text(encoding="utf-8")
        return template.replace("{tools}", self._format_tools_for_prompt()).strip()

    def _format_tools_for_prompt(self) -> str:
        """Format discovered MCP tools for insertion into the prompt template."""
        lines = []
        for tool in self.available_tools:
            desc_lines = (tool.description or "").strip().split("\n")
            short_desc = desc_lines[0] if desc_lines else ""
            params_info = self._format_tool_parameters(tool)
            lines.append(f"- {tool.name}: {short_desc}{params_info}")
        return "\n".join(lines)

    def _format_tool_parameters(self, tool: Any) -> str:
        schema = getattr(tool, "inputSchema", None)
        if not isinstance(schema, dict):
            return ""

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if not properties:
            return ""

        param_details = []
        for param_name, param_schema in properties.items():
            param_type = param_schema.get("type", "any")
            param_desc = param_schema.get("description", "")
            detail = f"'{param_name}' ({param_type}"
            if param_name in required:
                detail += ", required"
            detail += ")"
            if param_desc:
                detail += f": {param_desc}"
            param_details.append(detail)

        return f" - Parameters: {', '.join(param_details)}"

    def create_system_prompt(self) -> str:
        """Create the system prompt used for tool-aware LLM calls."""
        return self.create_tools_prompt()

    def create_tool_reasoning_prompt(self, question: str) -> str:
        """Create the fallback prompt used when deterministic routing finds no tool."""
        return self.create_system_prompt()

    def format_available_tools(self) -> str:
        """Render available tools with their full MCP description values."""
        if not self.available_tools:
            return "No tools are currently available from the connected MCP server."

        lines = [f"Available tools ({len(self.available_tools)}):"]
        for tool in self.available_tools:
            description = (tool.description or "").strip()
            if description:
                lines.append(f"- {tool.name}:\n{description}")
            else:
                lines.append(f"- {tool.name}")
        return "\n\n".join(lines)

    def is_list_tools_request(self, question: str) -> bool:
        """Detect explicit requests for tool lists or tool usage details."""
        q = question.strip().lower()
        return any(re.search(pattern, q) for pattern in self._load_tool_patterns())

    def _load_tool_patterns(self) -> List[str]:
        """Load tool-discovery request regex patterns from patterns.txt."""
        patterns_path = Path(__file__).with_name("patterns.txt")
        return [
            line.strip()
            for line in patterns_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def discover_tool_call(self, question: str) -> Tuple[Optional[str], Optional[dict]]:
        """Hook for subclasses to select tool calls before asking the LLM."""
        return None, None

    def recover_tool_call_after_llm_failure(
        self, question: str
    ) -> Tuple[Optional[str], Optional[dict]]:
        """Hook for subclasses to recover a tool call when the LLM returns no response."""
        return None, None

    def parse_tool_call(self, response: str) -> Tuple[Optional[str], Optional[dict], Optional[str]]:
        """Parse and validate tool call JSON from an LLM response."""
        if not response:
            return None, None, None

        start = response.find("{")
        end = response.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None, None, None

        try:
            parsed = json.loads(response[start : end + 1])
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

    async def execute_tool(self, tool_name: str, arguments: Optional[dict] = None):
        """Execute an MCP tool through the configured client."""
        try:
            tool_schema = None
            for tool in self.available_tools:
                if tool.name == tool_name:
                    tool_schema = tool.inputSchema
                    break

            if tool_schema and isinstance(tool_schema, dict):
                required_props = tool_schema.get("properties", {})
                if not required_props:
                    arguments = {}

            if arguments is None:
                arguments = {}

            return await self.client.call_tool(tool_name, arguments)
        except Exception as e:
            print(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}

    def normalize_tool_result(self, tool_result: Any) -> Any:
        """Normalize MCP tool results into plain Python data when possible."""
        content_attr = getattr(tool_result, "content", None)
        if content_attr is not None:
            parsed_content = self._parse_tool_content(content_attr)
            if parsed_content is not None:
                return parsed_content

        if hasattr(tool_result, "model_dump"):
            tool_result = tool_result.model_dump()

        if not isinstance(tool_result, dict):
            return tool_result

        structured = tool_result.get("structuredContent")
        if structured is not None:
            return structured

        parsed_content = self._parse_tool_content(tool_result.get("content"))
        if parsed_content is not None:
            return parsed_content

        return tool_result

    def _parse_tool_content(self, content: Any) -> Any:
        if not isinstance(content, list) or len(content) != 1:
            return None

        item = content[0]
        text = None
        if isinstance(item, dict):
            text = item.get("text")
        elif hasattr(item, "text"):
            text = item.text

        if not isinstance(text, str):
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def tool_result_has_error(self, tool_result: Any) -> bool:
        """Return True when a normalized tool result represents an error."""
        if isinstance(tool_result, dict):
            return bool(tool_result.get("isError")) or "error" in tool_result
        return False

    def format_tool_result_response(
        self, tool_name: str, tool_result: Any, arguments: Optional[dict] = None
    ) -> str:
        """Render successful tool output in a generic structured form."""
        if isinstance(tool_result, (dict, list)):
            return json.dumps(tool_result, indent=2, default=str)
        return str(tool_result)

    def query_llm(self, prompt: str) -> Optional[str]:
        """Query the configured LLM provider."""
        self._last_llm_prompt = prompt
        response = self.llm.generate(prompt, self.conversation_history)
        self._last_llm_response = response
        return response

    def is_token_usage_request(self, question: str) -> bool:
        """Detect requests to include token usage with the answer."""
        q = question.strip().lower()
        patterns = [
            r"\btoken usage\b",
            r"\btokens? used\b",
            r"\btoken count\b",
            r"\bprompt tokens?\b",
            r"\bresponse tokens?\b",
            r"\bcompletion tokens?\b",
            r"\bhow many tokens?\b",
        ]
        return any(re.search(pattern, q) for pattern in patterns)

    def reset_token_usage_tracking(self):
        """Reset per-question LLM usage tracking."""
        self._last_llm_prompt = None
        self._last_llm_response = None
        if hasattr(self.llm, "last_usage"):
            self.llm.last_usage = None

    def count_text_tokens(self, text: Optional[str]) -> int:
        """Approximate token count when the LLM backend does not report usage."""
        if not text:
            return 0
        return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))

    def get_token_usage(self, answer: str) -> Dict[str, Any]:
        """Return prompt/response token usage for the current question."""
        provider_usage = getattr(self.llm, "last_usage", None)
        if isinstance(provider_usage, dict):
            prompt_tokens = provider_usage.get("prompt_tokens", 0)
            response_tokens = provider_usage.get("response_tokens", 0)
            total_tokens = provider_usage.get("total_tokens", prompt_tokens + response_tokens)
            source = "provider"
        else:
            prompt_tokens = self.count_text_tokens(self._last_llm_prompt)
            response_text = self._last_llm_response if self._last_llm_response is not None else answer
            response_tokens = self.count_text_tokens(response_text)
            total_tokens = prompt_tokens + response_tokens
            source = "estimated"

        return {
            "prompt_tokens": prompt_tokens,
            "response_tokens": response_tokens,
            "total_tokens": total_tokens,
            "source": source,
            "llm_called": self._last_llm_prompt is not None,
        }

    def append_token_usage_if_requested(self, question: str, answer: str) -> str:
        """Append token usage when explicitly requested by the user."""
        if not self.is_token_usage_request(question):
            return answer

        usage = self.get_token_usage(answer)
        lines = [
            "",
            "Token usage:",
            f"- Prompt tokens: {usage['prompt_tokens']}",
            f"- Response tokens: {usage['response_tokens']}",
            f"- Total tokens: {usage['total_tokens']}",
            f"- Source: {usage['source']}",
        ]
        if not usage["llm_called"]:
            lines.append("- Note: no LLM prompt was sent; the answer was produced by deterministic tool routing/formatting.")
        return answer + "\n" + "\n".join(lines)

    async def process_question(self, question: str):
        """Process a user question using the configured LLM and MCP tools."""
        self.reset_token_usage_tracking()

        if self.is_list_tools_request(question):
            response = self.format_available_tools()
            response = self.append_token_usage_if_requested(question, response)
            print(f"Agent: {response}")
            return response

        tool_name, arguments = self.discover_tool_call(question)
        parse_error = None
        response = None

        if not tool_name:
            system_prompt = self.create_tool_reasoning_prompt(question)
            full_prompt = f"{system_prompt}\n\nUser question: {question}"
            response = self.query_llm(full_prompt)

            if not response:
                tool_name, arguments = self.recover_tool_call_after_llm_failure(question)
                if not tool_name:
                    msg = (
                        "Failed to get response from LLM. "
                        "Try asking for available tools, or use an explicit tool call JSON."
                    )
                    msg = self.append_token_usage_if_requested(question, msg)
                    print(f"Agent: {msg}")
                    return msg
            else:
                tool_name, arguments, parse_error = self.parse_tool_call(response)

        if parse_error:
            parse_error = self.append_token_usage_if_requested(question, parse_error)
            print(f"Agent: {parse_error}")
            return parse_error

        if tool_name:
            known_tools = {tool.name for tool in self.available_tools}
            if tool_name not in known_tools:
                msg = (
                    f"Tool '{tool_name}' is not available on this MCP server.\n"
                    f"{self.format_available_tools()}"
                )
                msg = self.append_token_usage_if_requested(question, msg)
                print(f"Agent: {msg}")
                return msg

            print(f"Agent: Using tool '{tool_name}'...")
            raw_tool_result = await self.execute_tool(tool_name, arguments)
            tool_result = self.normalize_tool_result(raw_tool_result)

            if self.tool_result_has_error(tool_result):
                error_msg = f"Failed to execute tool {tool_name}."
                if isinstance(tool_result, dict) and "error" in tool_result:
                    error_msg += f" Error: {tool_result['error']}"
                error_msg = self.append_token_usage_if_requested(question, error_msg)
                print(f"Agent: {error_msg}")
                return error_msg

            final_response = self.format_tool_result_response(tool_name, tool_result, arguments)
            final_response = self.append_token_usage_if_requested(question, final_response)
            print(f"Agent: {final_response}")
            return final_response

        final_response = self.append_token_usage_if_requested(question, response or "")
        print(f"Agent: {final_response}")
        return final_response

    def add_to_history(self, role: str, content: str):
        """Add a message to conversation history."""
        self.conversation_history.append({"role": role, "content": content})
