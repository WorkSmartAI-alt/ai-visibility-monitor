from __future__ import annotations

ENGINE_REGISTRY: dict[str, dict] = {
    "claude": {
        "module": "avm.engines.claude",
        "default_model": "claude-haiku-4-5-20251001",
        "api_key_env": "ANTHROPIC_API_KEY",
        "label": "Claude",
    },
    "chatgpt": {
        "module": "avm.engines.chatgpt",
        "default_model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "label": "ChatGPT",
    },
    "perplexity": {
        "module": "avm.engines.perplexity",
        "default_model": "sonar",
        "api_key_env": "PERPLEXITY_API_KEY",
        "label": "Perplexity",
    },
}

ENGINE_ORDER = ["claude", "chatgpt", "perplexity"]
