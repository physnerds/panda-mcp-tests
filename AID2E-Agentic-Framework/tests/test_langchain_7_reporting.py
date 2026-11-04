from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage


REPOSITORY = Path(__file__).resolve().parents[1]


def _load_example():
    path = REPOSITORY / "langchain-tests" / "test-langchain-7.py"
    spec = importlib.util.spec_from_file_location("aid2e_langchain_7", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_token_usage_prefers_usage_metadata_without_double_counting() -> None:
    module = _load_example()
    usage = module.TokenUsage()
    result = {
        "messages": [
            HumanMessage(content="summarize"),
            AIMessage(
                content="summary",
                usage_metadata={
                    "input_tokens": 11,
                    "output_tokens": 4,
                    "total_tokens": 15,
                },
                response_metadata={
                    "token_usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 4,
                    }
                },
            ),
        ]
    }

    assert usage.add_result(result) == (11, 4)
    assert (usage.input_tokens, usage.output_tokens) == (11, 4)


def test_token_usage_falls_back_to_openai_response_metadata() -> None:
    module = _load_example()
    usage = module.TokenUsage()
    result = {
        "messages": [
            AIMessage(
                content="summary",
                response_metadata={
                    "token_usage": {
                        "prompt_tokens": 7,
                        "completion_tokens": 3,
                    }
                },
            )
        ]
    }

    assert usage.add_result(result) == (7, 3)
    assert (usage.input_tokens, usage.output_tokens) == (7, 3)


def test_environment_flag_defaults_and_parses(monkeypatch) -> None:
    module = _load_example()
    monkeypatch.delenv("AID2E_TEST_FLAG", raising=False)
    assert module._env_flag("AID2E_TEST_FLAG") is False
    monkeypatch.setenv("AID2E_TEST_FLAG", "yes")
    assert module._env_flag("AID2E_TEST_FLAG") is True
    monkeypatch.setenv("AID2E_TEST_FLAG", "0")
    assert module._env_flag("AID2E_TEST_FLAG") is False
