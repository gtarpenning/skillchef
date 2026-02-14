from __future__ import annotations

from types import SimpleNamespace

from skillchef import llm


def test_selected_key_prefers_configured_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")

    assert llm.selected_key("OPENAI_API_KEY") == ("OPENAI_API_KEY", "OpenAI")
    assert llm.selected_key("NOT_PRESENT") == ("ANTHROPIC_API_KEY", "Anthropic")


def test_semantic_merge_uses_selected_api_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="merged output"))]
        )

    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(llm.config, "load", lambda: {"model": "openai/gpt-5-mini", "llm_api_key_env": "OPENAI_API_KEY"})
    monkeypatch.setattr(llm, "completion", fake_completion)

    result = llm.semantic_merge("old", "new", "flavor")

    assert result == "merged output"
    assert captured["api_key"] == "openai-token"


def test_semantic_merge_uses_ollama_api_base(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="merged output"))]
        )

    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost:11434")
    monkeypatch.setattr(llm.config, "load", lambda: {"model": "ollama/llama3", "llm_api_key_env": "OLLAMA_API_BASE"})
    monkeypatch.setattr(llm, "completion", fake_completion)

    result = llm.semantic_merge("old", "new", "flavor")

    assert result == "merged output"
    assert captured["api_base"] == "http://localhost:11434"
