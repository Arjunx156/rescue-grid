"""One door to every model. Pick the provider with LLM_PROVIDER; callers never import a vendor SDK.

`generate` returns a validated pydantic object or raises LLMError; it retries once
with the validation error attached, and backs off only on 429 and 5xx.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.core.logging import log
from app.core.settings import get_settings

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"


class LLMError(Exception):
    pass


class RetryableError(LLMError):
    """429 or 5xx: worth waiting and trying again."""


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


class _Throttle:
    """Spaces calls to stay under the provider's free-tier requests per minute."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self, rpm: int) -> None:
        if rpm <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + 60.0 / rpm
        if delay > 0:
            await asyncio.sleep(delay)


_throttle = _Throttle()


async def generate[T: BaseModel](system: str, user: str, schema: type[T]) -> tuple[T, dict[str, object]]:
    """(parsed output, usage) from the configured provider."""
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "local":
        raise LLMError("no model configured (LLM_PROVIDER=local)")
    if not settings.llm_model:
        raise LLMError(f"LLM_MODEL is empty for provider {provider}")

    if provider == "gemini":
        from app.llm import gemini as backend
    else:
        from app.llm import ollama as backend

    attempt_user = user
    for attempt in range(4):
        await _throttle.wait(settings.llm_max_rpm if provider == "gemini" else 0)
        started = time.perf_counter()
        try:
            raw, usage = await asyncio.wait_for(
                backend.complete(system, attempt_user, schema), timeout=settings.llm_timeout_s
            )
        except RetryableError as e:
            wait = min(30.0, 2.0 * 2**attempt)
            log.warning("llm.retry", provider=provider, attempt=attempt, wait_s=wait, error=str(e))
            await asyncio.sleep(wait)
            continue
        except TimeoutError as e:
            raise LLMError(f"{provider} timed out after {settings.llm_timeout_s}s") from e
        latency = int((time.perf_counter() - started) * 1000)
        log.info("llm.call", provider=provider, model=settings.llm_model, latency_ms=latency, cost_usd=0.0, **usage)
        try:
            return schema.model_validate_json(raw), {**usage, "latency_ms": latency}
        except ValidationError as e:
            if attempt_user is not user:
                raise LLMError(f"invalid output after retry: {e.errors()[:3]}") from e
            attempt_user = (
                f"{user}\n\nYour previous answer failed validation:\n{e}\nReturn JSON that matches the schema exactly."
            )
    raise LLMError(f"{provider} kept rate-limiting or failing")


async def embed(texts: list[str]) -> list[list[float]] | None:
    """Unit vectors of length 768, or None when no embedding model is configured."""
    settings = get_settings()
    if settings.llm_provider == "local" or not settings.embed_model or not texts:
        return None
    if settings.llm_provider == "gemini":
        from app.llm import gemini as backend
    else:
        from app.llm import ollama as backend
    try:
        await _throttle.wait(settings.llm_max_rpm if settings.llm_provider == "gemini" else 0)
        vectors = await asyncio.wait_for(backend.embed(texts), timeout=settings.llm_timeout_s)
    except (LLMError, TimeoutError) as e:
        log.warning("llm.embed_failed", error=str(e))
        return None
    out = []
    for v in vectors:
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / norm for x in v])
    return out
