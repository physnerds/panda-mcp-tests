from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import requests


class LLMProvider(ABC):
    """Unified API for local or remote LLM backends."""

    last_usage: Optional[Dict[str, int]] = None

    @abstractmethod
    def generate(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[str]:
        """Return model-generated text for a prompt."""

    @abstractmethod
    def info(self) -> Dict[str, str]:
        """Return provider metadata for logging and display."""


class OllamaProvider(LLMProvider):
    """LLM provider for Ollama chat models."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.last_usage: Optional[Dict[str, int]] = None

    def generate(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[str]:
        messages = (conversation_history or []) + [{"role": "user", "content": prompt}]
        payload = {"model": self.model, "messages": messages, "stream": False}

        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            prompt_tokens = data.get("prompt_eval_count")
            response_tokens = data.get("eval_count")
            if isinstance(prompt_tokens, int) or isinstance(response_tokens, int):
                prompt_tokens = prompt_tokens or 0
                response_tokens = response_tokens or 0
                self.last_usage = {
                    "prompt_tokens": prompt_tokens,
                    "response_tokens": response_tokens,
                    "total_tokens": prompt_tokens + response_tokens,
                }
            else:
                self.last_usage = None
            return data.get("message", {}).get("content", "")
        except Exception as e:
            print(f"Error querying Ollama: {e}")
            return None

    def info(self) -> Dict[str, str]:
        return {"provider": "Ollama", "model": self.model, "url": self.base_url}


class GPTOSSProvider(OllamaProvider):
    """LLM provider for the local gpt-oss Ollama model."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "gpt-oss:20b",
    ):
        super().__init__(base_url=base_url, model=model)

    def info(self) -> Dict[str, str]:
        return {"provider": "GPT-OSS via Ollama", "model": self.model, "url": self.base_url}


class VLLMProvider(LLMProvider):
    """LLM provider for vLLM completions endpoints."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1/completions",
        model: str = "meta-llama/Llama-3.3-70B-Instruct",
        max_tokens: int = 512,
        temperature: float = 0.7,
    ):
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.last_usage: Optional[Dict[str, int]] = None

    def generate(
        self, prompt: str, conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> Optional[str]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        try:
            response = requests.post(self.base_url, json=payload)
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage")
            if isinstance(usage, dict):
                prompt_tokens = usage.get("prompt_tokens") or 0
                response_tokens = usage.get("completion_tokens") or 0
                total_tokens = usage.get("total_tokens") or prompt_tokens + response_tokens
                self.last_usage = {
                    "prompt_tokens": prompt_tokens,
                    "response_tokens": response_tokens,
                    "total_tokens": total_tokens,
                }
            else:
                self.last_usage = None
            return data.get("choices", [{}])[0].get("text", "").strip()
        except Exception as e:
            print(f"Error querying vLLM: {e}")
            return None

    def info(self) -> Dict[str, str]:
        return {"provider": "vLLM", "model": self.model, "url": self.base_url}


def llm_provider(
    use_ollama: bool = True,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "mistral",
    use_gpt_oss: bool = False,
    gpt_oss_model: str = "gpt-oss:20b",
    use_vllm: bool = False,
    vllm_url: str = "http://localhost:8000/v1/completions",
    vllm_model: str = "meta-llama/Llama-3.3-70B-Instruct",
    **kwargs,
) -> LLMProvider:
    """Factory for the configured LLM backend.

    The default remains Ollama. Set use_vllm=True to select vLLM.
    Set use_gpt_oss=True to select the local gpt-oss Ollama model.
    The use_llama and llama_url keyword aliases are accepted for callers that
    refer to the local Ollama-backed model as llama.
    """
    if "use_llama" in kwargs:
        use_ollama = kwargs["use_llama"]
    if "llama_url" in kwargs:
        ollama_url = kwargs["llama_url"]
    if "use_gptoss" in kwargs:
        use_gpt_oss = kwargs["use_gptoss"]
    if "gpt_oss_url" in kwargs:
        ollama_url = kwargs["gpt_oss_url"]

    if use_vllm:
        return VLLMProvider(
            base_url=vllm_url,
            model=vllm_model,
            max_tokens=kwargs.get("max_tokens", 512),
            temperature=kwargs.get("temperature", 0.7),
        )

    if use_gpt_oss:
        return GPTOSSProvider(base_url=ollama_url, model=gpt_oss_model)

    if use_ollama:
        return OllamaProvider(base_url=ollama_url, model=ollama_model)

    raise ValueError("No LLM backend selected. Enable use_ollama, use_gpt_oss, or use_vllm.")
