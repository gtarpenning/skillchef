from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from skillchef import llm


def test_selected_key_prefers_configured_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")

    assert llm.selected_key("OPENAI_API_KEY") == ("OPENAI_API_KEY", "OpenAI")
    assert llm.selected_key("NOT_PRESENT") == ("ANTHROPIC_API_KEY", "Anthropic")


def test_default_model_for_key_uses_provider_defaults() -> None:
    assert llm.default_model_for_key("OPENAI_API_KEY") == "openai/gpt-5.2"
    assert llm.default_model_for_key("ANTHROPIC_API_KEY") == "anthropic/claude-sonnet-4-5"
    assert llm.default_model_for_key("GEMINI_API_KEY") == "gemini/gemini-2.5-flash"
    assert llm.default_model_for_key("MISTRAL_API_KEY") == "mistral/mistral-medium-latest"
    assert llm.default_model_for_key("COHERE_API_KEY") == "cohere/command-r-plus-08-2024"
    assert llm.default_model_for_key("UNKNOWN") == "anthropic/claude-sonnet-4-5"


def test_semantic_merge_uses_selected_api_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="merged output"))]
        )

    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        llm.config,
        "load",
        lambda scope="global": {"model": "openai/gpt-5.2", "llm_api_key_env": "OPENAI_API_KEY"},
    )
    monkeypatch.setattr(llm, "completion", fake_completion)

    result = llm.semantic_merge("old", "new", "flavor")

    assert result == "merged output"
    assert captured["api_key"] == "openai-token"
    assert "temperature" not in captured


def test_semantic_merge_uses_ollama_api_base(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="merged output"))]
        )

    monkeypatch.setenv("OLLAMA_API_BASE", "http://localhost:11434")
    monkeypatch.setattr(
        llm.config,
        "load",
        lambda scope="global": {"model": "ollama/llama3", "llm_api_key_env": "OLLAMA_API_BASE"},
    )
    monkeypatch.setattr(llm, "completion", fake_completion)

    result = llm.semantic_merge("old", "new", "flavor")

    assert result == "merged output"
    assert captured["api_base"] == "http://localhost:11434"


def test_semantic_merge_aligns_model_with_selected_key(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="merged output"))]
        )

    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        llm.config,
        "load",
        lambda scope="global": {
            "model": "anthropic/claude-sonnet-4-5",
            "llm_api_key_env": "OPENAI_API_KEY",
        },
    )
    monkeypatch.setattr(llm, "completion", fake_completion)

    result = llm.semantic_merge("old", "new", "flavor")

    assert result == "merged output"
    assert captured["api_key"] == "openai-token"
    assert captured["model"] == "openai/gpt-5.2"


def test_semantic_merge_appends_log_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setenv("SKILLCHEF_LLM_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(
        llm.config,
        "load",
        lambda scope="global": {"model": "openai/gpt-5.2", "llm_api_key_env": "OPENAI_API_KEY"},
    )
    monkeypatch.setattr(
        llm,
        "completion",
        lambda **_kwargs: SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="merged output"))]
        ),
    )

    result = llm.semantic_merge("old", "new", "flavor")
    log_text = (tmp_path / "logs" / "llm-completions.log").read_text()

    assert result == "merged output"
    assert "model: openai/gpt-5.2" in log_text
    assert "=== OLD BASE ===" in log_text
    assert "merged output" in log_text


def test_wizard_chat_uses_selected_key_and_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Jeremy answer"))]
        )

    monkeypatch.setenv("OPENAI_API_KEY", "openai-token")
    monkeypatch.setattr(
        llm.config,
        "load",
        lambda scope="global": {"model": "openai/gpt-5.2", "llm_api_key_env": "OPENAI_API_KEY"},
    )
    monkeypatch.setattr(llm, "completion", fake_completion)

    result = llm.wizard_chat(
        "What happens here?",
        step_label="Step 2/4 - Add local flavor",
        step_context="Flavor is written and live is rebuilt.",
        project_context="[AGENTS.md]\\nTest context",
    )

    assert result == "Jeremy answer"
    assert captured["api_key"] == "openai-token"
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "system"
    assert "Chef Jeremy" in messages[0]["content"]
    assert "Step 2/4 - Add local flavor" in messages[1]["content"]
