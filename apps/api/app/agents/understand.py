"""detect language -> extract -> validate -> ground -> reconcile.

Rules always run: they are instant, offline, and the only thing that sees phone
numbers. A model, when configured, reads the redacted text and must quote the
words behind every person, condition and level it adds; unquoted claims are
dropped (app.agents.guard). The two are then merged safety-first (a condition
either one noticed is kept). If the model fails, the rule result stands and the
case is flagged for a human read. A message that tries to instruct the system is
flagged as well.
"""

from __future__ import annotations

from app.agents import guard, rules
from app.core.logging import log
from app.core.settings import get_settings
from app.llm import LLMError, generate, prompt
from app.schemas.extraction import WATER_RANK, SosExtraction, Understanding, Vulnerable

RULES_MODEL = "rules-v1"


def reconcile(model: SosExtraction, ruled: SosExtraction) -> SosExtraction:
    mv, rv = model.vulnerable, ruled.vulnerable
    vulnerable = Vulnerable(
        elderly=max(mv.elderly, rv.elderly),
        child=max(mv.child, rv.child),
        infant=max(mv.infant, rv.infant),
        pregnant=max(mv.pregnant, rv.pregnant),
        disabled=max(mv.disabled, rv.disabled),
        medical=sorted(set(mv.medical) | set(rv.medical)),
    )
    water = model.water_level
    if WATER_RANK.get(ruled.water_level, 0) > WATER_RANK.get(water, 0):
        water = ruled.water_level
    merged = model.model_copy(
        update={
            "vulnerable": vulnerable,
            "water_level": water,
            "water_rising": model.water_rising or ruled.water_rising,
            "people_count": model.people_count or ruled.people_count,
            "needs": list(dict.fromkeys([*model.needs, *ruled.needs])),
            "address": model.address or ruled.address,
            "location_text": model.location_text or ruled.location_text,
            # script detection beats a model guess for native-script text
            "language": ruled.language if ruled.language != "en" else model.language,
        }
    )
    if merged.status_update == "none" and ruled.status_update != "none":
        merged.status_update = ruled.status_update
    return merged


async def understand(text: str) -> Understanding:
    ruled, phones = rules.extract(text)
    flags = guard.instructions_to_system(text)
    settings = get_settings()
    if settings.llm_provider == "local":
        return Understanding(extraction=ruled, phones=phones, provider="local", model=RULES_MODEL, flags=flags)
    redacted = rules.redact_phones(text)
    try:
        parsed, usage = await generate(prompt("extract"), redacted, SosExtraction)
    except LLMError as e:
        log.warning("understand.fallback", error=str(e))
        return Understanding(
            extraction=ruled,
            phones=phones,
            provider="local",
            model=RULES_MODEL,
            fallback_reason=str(e),
            flags=flags,
        )
    grounded, dropped = guard.ground(parsed, ruled, redacted)
    if dropped:
        log.warning("understand.ungrounded", dropped=dropped, model=settings.llm_model)
    merged = reconcile(grounded, ruled)
    if not merged.summary:
        merged.summary = rules.summarize(merged)
    return Understanding(
        extraction=merged,
        phones=phones,
        provider=settings.llm_provider,
        model=settings.llm_model,
        latency_ms=int(usage.get("latency_ms", 0) or 0),  # type: ignore[call-overload]
        dropped_claims=dropped,
        flags=flags,
    )
