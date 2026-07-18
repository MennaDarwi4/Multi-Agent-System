"""
Provider-agnostic LLM client.

Design goals (maps to objective 6 - reliability):
  * One `chat()` interface regardless of provider (Groq / OpenAI / Anthropic).
  * A model fallback chain: if the primary model errors or rate-limits, try the
    next model in the chain before giving up.
  * Graceful offline degradation: if there is no key / no network, callers can
    fall back to extractive (non-LLM) logic instead of crashing.

The client lazily imports the provider SDK so the app still starts even if a
particular SDK is not installed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from config import Settings, settings as default_settings


class LLMError(RuntimeError):
    """Raised when every model in the fallback chain fails."""


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    latency_s: float
    used_fallback: bool = False
    attempts: List[str] = field(default_factory=list)


class LLMClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.s = settings or default_settings

    # -- public API --------------------------------------------------------
    @property
    def available(self) -> bool:
        """True if we have a key for the configured provider."""
        return self.s.provider != "offline" and self.s.has_llm_key()

    def chat(self, system: str, user: str) -> LLMResult:
        """
        Send a system+user prompt through the fallback chain.
        Raises LLMError if all models fail (callers should catch and degrade).
        """
        if not self.available:
            raise LLMError(
                f"No API key configured for provider '{self.s.provider}'. "
                "Set the key or use extractive fallback."
            )

        models = self.s.active_models()
        attempts: List[str] = []
        last_err: Optional[Exception] = None

        for idx, model in enumerate(models):
            attempts.append(model)
            t0 = time.time()
            try:
                text = self._dispatch(model, system, user)
                return LLMResult(
                    text=text.strip(),
                    model=model,
                    provider=self.s.provider,
                    latency_s=round(time.time() - t0, 3),
                    used_fallback=idx > 0,
                    attempts=attempts,
                )
            except Exception as e:  # noqa: BLE001 - we intentionally try next model
                last_err = e
                # brief backoff before trying the fallback model
                time.sleep(0.5)
                continue

        raise LLMError(
            f"All models failed for provider '{self.s.provider}'. "
            f"Tried {attempts}. Last error: {last_err}"
        )

    # -- provider dispatch -------------------------------------------------
    def _dispatch(self, model: str, system: str, user: str) -> str:
        if self.s.provider == "groq":
            return self._groq(model, system, user)
        if self.s.provider == "openai":
            return self._openai(model, system, user)
        if self.s.provider == "anthropic":
            return self._anthropic(model, system, user)
        raise LLMError(f"Unknown provider: {self.s.provider}")

    def _groq(self, model: str, system: str, user: str) -> str:
        from groq import Groq

        client = Groq(api_key=self.s.groq_api_key, timeout=self.s.request_timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.s.temperature,
            max_tokens=self.s.max_tokens,
        )
        return resp.choices[0].message.content or ""

    def _openai(self, model: str, system: str, user: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.s.openai_api_key, timeout=self.s.request_timeout)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=self.s.temperature,
            max_tokens=self.s.max_tokens,
        )
        return resp.choices[0].message.content or ""

    def _anthropic(self, model: str, system: str, user: str) -> str:
        import anthropic

        client = anthropic.Anthropic(
            api_key=self.s.anthropic_api_key, timeout=self.s.request_timeout
        )
        resp = client.messages.create(
            model=model,
            system=system,
            max_tokens=self.s.max_tokens,
            temperature=self.s.temperature,
            messages=[{"role": "user", "content": user}],
        )
        # concatenate text blocks
        return "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
