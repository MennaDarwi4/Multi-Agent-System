"""
Central configuration for the Multi-Agent AI System.

Reads settings from environment variables (or a .env file) so that no secret
is ever hard-coded. Everything has a sensible default so the app also runs in
a fully offline / no-key "demo" mode.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

try:
    # optional: load a local .env if present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional
    pass


@dataclass
class Settings:
    # ---- LLM provider ----------------------------------------------------
    # provider: "groq" | "openai" | "anthropic" | "offline"
    provider: str = os.getenv("LLM_PROVIDER", "groq").lower()

    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Fallback chain (first model is tried first, then the next on failure).
    # Mirrors a production-style router: strong model -> fast/cheap model.
    groq_models: List[str] = field(
        default_factory=lambda: [
            os.getenv("GROQ_PRIMARY_MODEL", "llama-3.3-70b-versatile"),
            os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant"),
        ]
    )
    openai_models: List[str] = field(
        default_factory=lambda: [os.getenv("OPENAI_MODEL", "gpt-4o-mini")]
    )
    anthropic_models: List[str] = field(
        default_factory=lambda: [os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")]
    )

    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "1024"))
    request_timeout: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # ---- Retrieval -------------------------------------------------------
    max_chars_per_source: int = int(os.getenv("MAX_CHARS_PER_SOURCE", "20000"))
    web_search_enabled: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"

    # ---- Orchestration ---------------------------------------------------
    parallel_workers: int = int(os.getenv("PARALLEL_WORKERS", "4"))

    # ---- Email (automated action) ---------------------------------------
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")

    def has_llm_key(self) -> bool:
        return bool(
            {
                "groq": self.groq_api_key,
                "openai": self.openai_api_key,
                "anthropic": self.anthropic_api_key,
            }.get(self.provider, "")
        )

    def active_models(self) -> List[str]:
        return {
            "groq": self.groq_models,
            "openai": self.openai_models,
            "anthropic": self.anthropic_models,
        }.get(self.provider, [])


# a singleton-ish default instance the app imports
settings = Settings()
