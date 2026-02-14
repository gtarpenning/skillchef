from __future__ import annotations

import os

from litellm import completion

from skillchef import config

LLM_KEY_MAP = [
    ("ANTHROPIC_API_KEY", "Anthropic"),
    ("OPENAI_API_KEY", "OpenAI"),
    ("GEMINI_API_KEY", "Google Gemini"),
    ("MISTRAL_API_KEY", "Mistral"),
    ("COHERE_API_KEY", "Cohere"),
    ("OLLAMA_API_BASE", "Ollama (local)"),
]

DEFAULT_MODEL_BY_KEY = {
    "ANTHROPIC_API_KEY": "anthropic/claude-sonnet-4-20250514",
    "OPENAI_API_KEY": "openai/gpt-5-mini",
    "GEMINI_API_KEY": "gemini/gemini-2.5-pro",
    "MISTRAL_API_KEY": "mistral/mistral-large-latest",
    "COHERE_API_KEY": "cohere/command-r-plus",
    "OLLAMA_API_BASE": "ollama/llama3.2",
}

MERGE_PROMPT = """You are merging an agent skill file. The upstream base has changed.
The user has a local "flavor" (customization) applied on top of the old base.

Your job: produce a single merged SKILL.md that incorporates BOTH the new upstream
changes AND the user's local flavor. Preserve the intent of both sides.

Return ONLY the merged file content, no explanation.

=== OLD BASE ===
{old_base}

=== NEW REMOTE (upstream update) ===
{new_remote}

=== USER'S LOCAL FLAVOR ===
{flavor}

=== MERGED RESULT ==="""


def detect_keys() -> list[tuple[str, str]]:
    return [(k, v) for k, v in LLM_KEY_MAP if os.environ.get(k)]


def selected_key(preferred_env_var: str | None = None) -> tuple[str, str] | None:
    keys = detect_keys()
    if not keys:
        return None
    if preferred_env_var:
        for env_var, provider in keys:
            if env_var == preferred_env_var:
                return env_var, provider
    return keys[0]


def default_model_for_key(env_var: str | None) -> str:
    return DEFAULT_MODEL_BY_KEY.get(env_var or "", "anthropic/claude-sonnet-4-20250514")


def has_llm() -> bool:
    return len(detect_keys()) > 0


def _provider_prefix(model: str) -> str:
    return model.split("/", 1)[0].strip().lower()


def _resolve_model(configured_model: str, env_var: str | None, model_override: str | None) -> str:
    if model_override:
        return model_override
    if not env_var:
        return configured_model

    expected = default_model_for_key(env_var)
    if _provider_prefix(configured_model) != _provider_prefix(expected):
        return expected
    return configured_model


def semantic_merge(old_base: str, new_remote: str, flavor: str, model: str | None = None) -> str:
    cfg = config.load()
    configured_model = cfg.get("model", "anthropic/claude-sonnet-4-20250514")
    configured_env = cfg.get("llm_api_key_env", "")
    key = selected_key(configured_env)
    env_var = key[0] if key else None
    model = _resolve_model(configured_model, env_var, model)

    completion_kwargs: dict[str, str | int | list[dict[str, str]]] = {}
    if key:
        env_var, _provider = key
        value = os.environ.get(env_var, "")
        if value:
            if env_var == "OLLAMA_API_BASE":
                completion_kwargs["api_base"] = value
            else:
                completion_kwargs["api_key"] = value

    prompt = MERGE_PROMPT.format(old_base=old_base, new_remote=new_remote, flavor=flavor)
    resp = completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        **completion_kwargs,
    )
    return resp.choices[0].message.content.strip()
