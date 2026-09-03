import requests
import json
import time

API_URL = "http://localhost:8000/v1/responses"
MODEL = "meta-llama/Llama-3.3-70B-Instruct"

def query_vllm(prompt, max_output_tokens=64):
    payload = {
        "model": MODEL,
        "input": prompt,
        "max_output_tokens": max_output_tokens,
    }

    t0 = time.time()
    response = requests.post(API_URL, json=payload, timeout=60)
    elapsed = time.time() - t0

    print(f"HTTP status: {response.status_code}")
    print(f"Elapsed: {elapsed:.2f} seconds")

    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    result = query_vllm(
        "Say hello in five words.",
        max_output_tokens=32,
    )
    print(json.dumps(result, indent=2))