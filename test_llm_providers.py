#!/usr/bin/env python3
"""
Example script demonstrating the modular LLM provider system.

This shows how to use different LLM backends (Ollama, vLLM) with the same interface.
Useful for testing providers independently from the full MCP agent.
"""

import asyncio
from llm_providers import OllamaProvider, VLLMProvider, LLMProvider


def test_provider(provider: LLMProvider, test_prompt: str = "What is 2+2? Answer concisely."):
    """Test a provider with a simple prompt."""
    print(f"\n{'='*60}")
    print(f"Testing: {provider.get_provider_name()}")
    print(f"{'='*60}")
    print(f"Prompt: {test_prompt}")
    print("-" * 60)
    
    response = provider.query(test_prompt)
    
    if response:
        print(f"Response: {response}")
        print("✓ SUCCESS")
    else:
        print("✗ FAILED - No response received")
    
    print(f"{'='*60}\n")
    return response


def test_conversation(provider: LLMProvider):
    """Test a provider with conversation history."""
    print(f"\n{'='*60}")
    print(f"Testing conversation with: {provider.get_provider_name()}")
    print(f"{'='*60}")
    
    history = []
    
    # Turn 1
    print("\nTurn 1:")
    print("User: My name is Alice.")
    response1 = provider.query("My name is Alice.", history)
    print(f"Assistant: {response1}")
    
    if response1:
        history.append({"role": "user", "content": "My name is Alice."})
        history.append({"role": "assistant", "content": response1})
    
    # Turn 2
    print("\nTurn 2:")
    print("User: What is my name?")
    response2 = provider.query("What is my name?", history)
    print(f"Assistant: {response2}")
    
    print(f"{'='*60}\n")


def main():
    """Run provider tests."""
    print("LLM Provider Test Suite")
    print("=" * 60)
    
    # Test 1: Local Ollama (Mistral)
    print("\n[Test 1] Local Ollama Provider")
    try:
        ollama = OllamaProvider(
            base_url="http://localhost:11434",
            model="mistral"
        )
        test_provider(ollama, "What is the capital of France? Answer in one word.")
        
        # Test conversation
        test_conversation(ollama)
    except Exception as e:
        print(f"✗ Ollama test failed: {e}")
        print("  Make sure Ollama is running: ollama serve")
    
    # Test 2: Remote vLLM (requires SSH tunnel)
    print("\n[Test 2] Remote vLLM Provider (via SSH tunnel)")
    print("  Prerequisites: ssh -N -L 8000:localhost:8000 perlmutter.nersc.gov")
    
    try:
        vllm = VLLMProvider(
            base_url="http://localhost:8000/v1/completions",
            model="meta-llama/Llama-3.3-70B-Instruct",
            max_tokens=50,
            temperature=0.7
        )
        test_provider(vllm, "What is 2+2? Answer concisely.")
    except Exception as e:
        print(f"✗ vLLM test failed: {e}")
        print("  Make sure SSH tunnel is active or vLLM server is accessible")
    
    print("\n" + "=" * 60)
    print("Test suite complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
