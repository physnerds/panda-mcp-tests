"""
LLM Provider abstractions for PanDA MCP Agent.

This module provides a pluggable interface for different LLM backends,
allowing the agent to work with local models (Ollama) or remote inference
servers (vLLM, OpenAI-compatible APIs, etc.).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import requests


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def query(self, prompt: str, conversation_history: Optional[List[Dict]] = None) -> Optional[str]:
        """
        Query the LLM with a prompt and optional conversation history.
        
        Args:
            prompt: The user prompt to send to the LLM
            conversation_history: Optional list of previous messages in format
                                 [{"role": "user|assistant", "content": "..."}]
        
        Returns:
            The LLM's response text, or None if the query failed
        """
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return a human-readable name for this provider."""
        pass


class OllamaProvider(LLMProvider):
    """Provider for local Ollama models (e.g., Mistral)."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral"):
        """
        Initialize Ollama provider.
        
        Args:
            base_url: Ollama server URL (default: http://localhost:11434)
            model: Model name to use (default: mistral)
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
    
    def query(self, prompt: str, conversation_history: Optional[List[Dict]] = None) -> Optional[str]:
        """Query Ollama server with chat completion API."""
        messages = (conversation_history or []) + [{"role": "user", "content": prompt}]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False
        }
        
        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            assistant_message = data.get("message", {}).get("content", "")
            return assistant_message
        except Exception as e:
            print(f"Error querying Ollama: {e}")
            return None
    
    def get_provider_name(self) -> str:
        return f"Ollama ({self.model})"


class VLLMProvider(LLMProvider):
    """Provider for vLLM inference servers (local or remote via SSH tunnel)."""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:8000/v1/completions",
        model: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 512,
        temperature: float = 0.7
    ):
        """
        Initialize vLLM provider.
        
        Args:
            base_url: vLLM completions endpoint (default: http://localhost:8000/v1/completions)
            model: Model identifier (default: meta-llama/Llama-3.3-70B-Instruct)
            max_tokens: Maximum tokens to generate (default: 512)
            temperature: Sampling temperature (default: 0.7)
        """
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    def query(self, prompt: str, conversation_history: Optional[List[Dict]] = None) -> Optional[str]:
        """
        Query vLLM server with completions API.
        
        Note: vLLM uses completions endpoint, not chat. Conversation history
        is incorporated into the prompt string.
        """
        # For vLLM completions API, merge conversation history into prompt
        if conversation_history:
            context = "\n".join([
                f"{msg['role'].capitalize()}: {msg['content']}" 
                for msg in conversation_history
            ])
            full_prompt = f"{context}\nUser: {prompt}\nAssistant:"
        else:
            full_prompt = prompt
        
        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            response = requests.post(self.base_url, json=payload)
            response.raise_for_status()
            data = response.json()
            # vLLM returns text in choices[0].text
            return data.get("choices", [{}])[0].get("text", "").strip()
        except Exception as e:
            print(f"Error querying vLLM: {e}")
            return None
    
    def get_provider_name(self) -> str:
        return f"vLLM ({self.model.split('/')[-1]})"


class OpenAICompatibleProvider(LLMProvider):
    """
    Provider for OpenAI-compatible APIs (OpenAI, Azure OpenAI, local OpenAI-compatible servers).
    
    This is a future extension point for cloud-hosted LLMs.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-4",
        max_tokens: int = 512,
        temperature: float = 0.7
    ):
        """
        Initialize OpenAI-compatible provider.
        
        Args:
            base_url: API base URL (e.g., https://api.openai.com/v1)
            api_key: API authentication key
            model: Model identifier (default: gpt-4)
            max_tokens: Maximum tokens to generate (default: 512)
            temperature: Sampling temperature (default: 0.7)
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
    
    def query(self, prompt: str, conversation_history: Optional[List[Dict]] = None) -> Optional[str]:
        """Query OpenAI-compatible chat completion endpoint."""
        messages = (conversation_history or []) + [{"role": "user", "content": prompt}]
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            print(f"Error querying OpenAI-compatible API: {e}")
            return None
    
    def get_provider_name(self) -> str:
        return f"OpenAI-compatible ({self.model})"
