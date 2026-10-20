from __future__ import annotations

from functools import lru_cache

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.core.settings import get_settings
from app.llm import LLMError, RetryableError

EMBED_DIM = 768


@lru_cache
def _client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set")
    return genai.Client(
        api_key=settings.gemini_api_key.get_secret_value(),
        http_options=types.HttpOptions(timeout=int(settings.llm_timeout_s * 1000)),
    )


def _raise(e: errors.APIError) -> None:
    if e.code == 429 or (e.code or 0) >= 500:
        raise RetryableError(f"gemini {e.code}: {e.message}") from e
    raise LLMError(f"gemini {e.code}: {e.message}") from e


async def complete(system: str, user: str, schema: type[BaseModel]) -> tuple[str, dict[str, object]]:
    try:
        resp = await _client().aio.models.generate_content(
            model=get_settings().llm_model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0,
            ),
        )
    except errors.APIError as e:
        _raise(e)
        raise
    meta = resp.usage_metadata
    usage: dict[str, object] = {
        "tokens_in": getattr(meta, "prompt_token_count", None),
        "tokens_out": getattr(meta, "candidates_token_count", None),
    }
    if not resp.text:
        raise LLMError("gemini returned no text (blocked or empty)")
    return resp.text, usage


async def embed(texts: list[str]) -> list[list[float]]:
    try:
        resp = await _client().aio.models.embed_content(
            model=get_settings().embed_model,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=EMBED_DIM, task_type="SEMANTIC_SIMILARITY"),
        )
    except errors.APIError as e:
        _raise(e)
        raise
    return [list(e.values or []) for e in resp.embeddings or []]
