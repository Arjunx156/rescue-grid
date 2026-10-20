from __future__ import annotations

from functools import lru_cache

import httpx
from ollama import AsyncClient, ResponseError
from pydantic import BaseModel

from app.core.settings import get_settings
from app.llm import LLMError, RetryableError


@lru_cache
def _client() -> AsyncClient:
    return AsyncClient(host=get_settings().ollama_host)


async def complete(system: str, user: str, schema: type[BaseModel]) -> tuple[str, dict[str, object]]:
    try:
        resp = await _client().chat(
            model=get_settings().llm_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            format=schema.model_json_schema(),
            options={"temperature": 0},
        )
    except ResponseError as e:
        if e.status_code >= 500 or e.status_code == 429:
            raise RetryableError(f"ollama {e.status_code}: {e.error}") from e
        raise LLMError(f"ollama {e.status_code}: {e.error}") from e
    except httpx.ConnectError as e:
        raise LLMError(f"ollama is not running at {get_settings().ollama_host}") from e
    usage: dict[str, object] = {"tokens_in": resp.prompt_eval_count, "tokens_out": resp.eval_count}
    return resp.message.content or "", usage


async def embed(texts: list[str]) -> list[list[float]]:
    try:
        resp = await _client().embed(model=get_settings().embed_model, input=texts)
    except (ResponseError, httpx.ConnectError) as e:
        raise LLMError(f"ollama embed failed: {e}") from e
    return [list(v) for v in resp.embeddings]
