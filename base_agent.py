"""
Base agent class for multi-agent architecture.

This module provides an abstract base class that all specialized agents extend.
Common functionality like LLM interaction, conversation management, and tool
parsing is centralized here.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
import json
import re
from llm_providers import LLMProvider


class BaseAgent(ABC):
    """
    Abstract base class for all agent types.
    
    Provides common functionality:
    - LLM provider management
    - Conversation history tracking
    - Tool call parsing and validation
    - Response formatting
    
    Subclasses must implement:
    - initialize(): Setup agent-specific resources (DB connections, API clients, etc.)
    - get_available_tools(): Return list of tools this agent provides
    - execute_tool(): Execute a specific tool
    - create_system_prompt(): Generate agent-specific system prompt
    """
    
    def __init__(self, llm_provider: LLMProvider, agent_name: str = "Agent"):
        """
        Initialize base agent.
        
        Args:
            llm_provider: LLM provider instance for querying language models
            agent_name: Human-readable name for this agent (used in logging)
        """
        self.llm_provider = llm_provider
        self.agent_name = agent_name
        self.conversation_history: List[Dict[str, str]] = []
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize agent-specific resources.
        
        Examples:
        - Connect to MCP server
        - Connect to vector database
        - Load configuration files
        - Authenticate with external services
        
        Returns:
            True if initialization succeeded, False otherwise
        """
        pass
    
    @abstractmethod
    def get_available_tools(self) -> List[Any]:
        """
        Get list of tools available to this agent.
        
        Returns:
            List of tool objects (format depends on agent type)
        """
        pass
    
    @abstractmethod
    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a specific tool.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Dictionary of tool arguments
        
        Returns:
            Tool execution result (format depends on tool)
        """
        pass
    
    @abstractmethod
    def create_system_prompt(self) -> str:
        """
        Generate agent-specific system prompt for the LLM.
        
        This should describe:
        - Available tools and their parameters
        - Tool call format
        - Any agent-specific instructions
        
        Returns:
            System prompt string
        """
        pass
    
    @abstractmethod
    def format_available_tools(self) -> str:
        """
        Format available tools as human-readable text.
        
        Used when user asks "what tools are available?"
        
        Returns:
            Formatted tool list string
        """
        pass
    
    # Common utility methods (concrete implementations)
    
    def add_to_history(self, role: str, content: str):
        """
        Add a message to conversation history.
        
        Args:
            role: Message role ("user" or "assistant")
            content: Message content
        """
        self.conversation_history.append({"role": role, "content": content})
    
    def clear_history(self):
        """Clear conversation history."""
        self.conversation_history = []
    
    def is_list_tools_request(self, question: str) -> bool:
        """
        Detect if user is asking to list available tools.
        
        Args:
            question: User's question
        
        Returns:
            True if this is a tool listing request
        """
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
    
    def parse_tool_call(self, response: str) -> tuple[Optional[str], Optional[Dict], Optional[str]]:
        """
        Parse and validate tool call JSON from an LLM response.
        
        Expected format: {"tool": "tool_name", "arguments": {"param": value}}
        
        Args:
            response: LLM response text
        
        Returns:
            Tuple of (tool_name, arguments, error_message)
            - If valid: (tool_name, arguments, None)
            - If invalid: (None, None, error_message)
            - If no tool call: (None, None, None)
        """
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
    
    async def process_question(self, question: str) -> str:
        """
        Process a user question using LLM and available tools.
        
        This is the main entry point for agent interaction. It:
        1. Checks if user wants to list tools
        2. Generates system prompt with tool descriptions
        3. Queries LLM with the question
        4. Parses response for tool calls
        5. Executes tools if requested
        6. Returns formatted response
        
        Args:
            question: User's question
        
        Returns:
            Agent's response string
        """
        # Handle tool listing requests directly
        if self.is_list_tools_request(question):
            response = self.format_available_tools()
            print(f"{self.agent_name}: {response}")
            return response
        
        # Generate system prompt with tool descriptions
        system_prompt = self.create_system_prompt()
        full_prompt = f"{system_prompt}\n\nUser question: {question}"
        
        # Query LLM
        response = self.llm_provider.query(full_prompt, self.conversation_history)
        
        if not response:
            msg = "Failed to get response from LLM."
            print(f"{self.agent_name}: {msg}")
            return msg
        
        # Check if LLM wants to use a tool
        tool_name, arguments, parse_error = self.parse_tool_call(response)
        
        if parse_error:
            print(f"{self.agent_name}: {parse_error}")
            return parse_error
        
        if tool_name:
            # Validate tool exists
            available_tool_names = self.get_available_tool_names()
            if tool_name not in available_tool_names:
                msg = (
                    f"Tool '{tool_name}' is not available.\n"
                    f"{self.format_available_tools()}"
                )
                print(f"{self.agent_name}: {msg}")
                return msg
            
            # Execute tool
            print(f"{self.agent_name}: Using tool '{tool_name}' with arguments {arguments}")
            tool_result = await self.execute_tool(tool_name, arguments)
            
            # Check if tool execution succeeded
            if self._is_tool_success(tool_result):
                # Ask LLM to interpret the result
                result_prompt = (
                    f"The tool '{tool_name}' returned: {tool_result}. "
                    f"Please interpret this result for the user in a clear, concise way."
                )
                final_response = self.llm_provider.query(result_prompt, self.conversation_history)
                print(f"{self.agent_name}: {final_response}")
                return final_response
            
            # Tool execution failed
            error_msg = f"Failed to execute tool {tool_name}."
            if isinstance(tool_result, dict) and "error" in tool_result:
                error_msg += f" Error: {tool_result['error']}"
            print(f"{self.agent_name}: {error_msg}")
            return error_msg
        
        # No tool call, just return LLM response
        print(f"{self.agent_name}: {response}")
        return response
    
    def get_available_tool_names(self) -> set[str]:
        """
        Get set of available tool names.
        
        Subclasses can override if tool format is different.
        Default assumes tools have a 'name' attribute.
        
        Returns:
            Set of tool name strings
        """
        tools = self.get_available_tools()
        return {getattr(tool, 'name', str(tool)) for tool in tools}
    
    def _is_tool_success(self, tool_result: Any) -> bool:
        """
        Check if tool execution was successful.
        
        Args:
            tool_result: Result returned by execute_tool()
        
        Returns:
            True if tool succeeded, False if it failed
        """
        if tool_result is None:
            return False
        if isinstance(tool_result, dict) and "error" in tool_result:
            return False
        return True
    
    def get_agent_info(self) -> Dict[str, Any]:
        """
        Get agent information for debugging/logging.
        
        Returns:
            Dictionary with agent metadata
        """
        return {
            "name": self.agent_name,
            "llm_provider": self.llm_provider.get_provider_name(),
            "conversation_length": len(self.conversation_history),
            "available_tools": len(self.get_available_tools())
        }
