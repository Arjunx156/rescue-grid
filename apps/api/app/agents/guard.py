"""What a model may change, and what a person must see.

Rules always read the message. A model may add detail on top, but only detail it can
quote: every person, condition, headcount or water level it claims beyond the rules
needs words that are really in the message. Anything else is dropped and logged, so
a hallucinated "dialysis" or an injected "40 people" never moves a boat.

Separately, a message that talks to the system ("ignore your instructions", "set
priority to 100") is flagged for a coordinator. It still goes through as data.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.schemas.extraction import WATER_RANK, SosExtraction

MIN_QUOTE = 4
MATCH = 90  # partial ratio: survives a typo, not an invention
COUNTED = ("elderly", "child", "infant", "pregnant", "disabled")

INSTRUCTIONS = re.compile(
    "|".join(
        (
            r"\bignore (?:all |any |the )?(?:previous|prior|above|earlier|your) (?:instructions?|rules|prompts?)",
            r"\bdisregard (?:all |any |the )?(?:previous|prior|above|your)",
            r"\bsystem ?(?:prompt|message|instruction)s?\b",
            r"^\s*(?:system|assistant|developer)\s*:",
            r"\byou are (?:now )?(?:an? )?(?:ai|assistant|language model|chatbot)\b",
            r"\b(?:set|change|raise) (?:the )?(?:urgency|priority|score|level)\b",
            r"\bmark (?:this|it|the case|this case) (?:as )?(?:critical|top priority)\b",
            r"\b(?:send|assign|dispatch) (?:all|every) (?:boats|teams|units)\b",
            r"<\|[a-z_]+\|>",
            r"#{2,}\s*instruction",
        )
    ),
    re.IGNORECASE | re.MULTILINE,
)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s\[\]]", " ", text.lower()).split())


def quoted(quote: str, text: str) -> bool:
    q, t = _norm(quote), _norm(text)
    if len(q) < MIN_QUOTE:
        return False
    return q in t or fuzz.partial_ratio(q, t) >= MATCH


def instructions_to_system(text: str) -> list[str]:
    return [m.group(0).strip() for m in INSTRUCTIONS.finditer(text)]


def ground(model: SosExtraction, ruled: SosExtraction, text: str) -> tuple[SosExtraction, list[str]]:
    """The model's extraction with every unquoted escalation beyond the rules taken back out."""
    backed = {e.field.strip().lower() for e in model.evidence if quoted(e.quote, text)}
    dropped: list[str] = []
    update: dict[str, object] = {}

    if model.people_count is not None and model.people_count != ruled.people_count and "people_count" not in backed:
        dropped.append(f"people_count: {model.people_count}")
        update["people_count"] = ruled.people_count
    if WATER_RANK.get(model.water_level, 0) > WATER_RANK.get(ruled.water_level, 0) and "water_level" not in backed:
        dropped.append(f"water_level: {model.water_level}")
        update["water_level"] = ruled.water_level

    vul = model.vulnerable.model_copy()
    for key in COUNTED:
        claimed, found = getattr(vul, key), getattr(ruled.vulnerable, key)
        if claimed > found and key not in backed:
            dropped.append(f"{key}: {claimed}")
            setattr(vul, key, found)
    keep = []
    for m in vul.medical:
        if m in ruled.vulnerable.medical or f"medical:{m}" in backed or "medical" in backed:
            keep.append(m)
        else:
            dropped.append(f"medical: {m}")
    vul.medical = keep
    update["vulnerable"] = vul
    return model.model_copy(update=update), dropped
