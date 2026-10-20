"""Rule-based SOS reader. Runs offline, in milliseconds, in five languages.

It is the default when no model is configured and the fallback when one fails,
so every message gets an extraction even with the network down.
"""

from __future__ import annotations

import re
import unicodedata

from app.agents import lexicon as lx
from app.schemas.extraction import WATER_RANK, SosExtraction, Vulnerable

_P = {
    "units": lx.PEOPLE_UNITS.pattern(),
    "kin": lx.KIN_SINGLE.pattern(),
    "kin_pair": lx.KIN_PAIR.pattern(),
    "elderly": lx.ELDERLY.pattern(),
    "child": lx.CHILD.pattern(),
    "infant": lx.INFANT.pattern(),
    "pregnant": lx.PREGNANT.pattern(),
    "disabled": lx.DISABLED.pattern(),
    "rising": lx.RISING.pattern(),
    "rescued": lx.RESCUED.pattern(),
    "false_alarm": lx.FALSE_ALARM.pattern(),
}
_MEDICAL = {k: t.pattern() for k, t in lx.MEDICAL.items()}
_WATER = {k: t.pattern() for k, t in lx.WATER.items()}
_NEEDS = {k: t.pattern() for k, t in lx.NEEDS.items()}
_ROMAN = {k: t.pattern() for k, t in lx.ROMAN_MARKERS.items()}
_COUNT_BEFORE_UNIT = re.compile(lx.NUM + r"\s*(?:-|\s)?\s*$", re.IGNORECASE)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[​-‍﻿]", "", text)  # zero-width joiners from phone keyboards
    return re.sub(r"\s+", " ", text).strip()


def to_number(token: str | None, *, strict: bool = False) -> int | None:
    if not token:
        return None
    token = token.strip().lower()
    if token.isdigit():
        n = int(token)
        return n if 0 < n <= 500 else None
    if strict and token in lx.WEAK_NUMBERS:
        return None
    return lx.NUMBER_WORDS.get(token)


def detect_language(text: str) -> str:
    counts = {lang: 0 for lang in lx.SCRIPTS}
    latin = 0
    for ch in text:
        cp = ord(ch)
        if ch.isascii() and ch.isalpha():
            latin += 1
            continue
        for lang, (lo, hi) in lx.SCRIPTS.items():
            if lo <= cp <= hi:
                counts[lang] += 1
                break
    script_lang, script_n = max(counts.items(), key=lambda kv: kv[1])
    if script_n and script_n >= latin * 0.3:
        return script_lang
    # romanised: count distinctive words per language
    hits = {lang: len(p.findall(text)) for lang, p in _ROMAN.items()}
    lang, n = max(hits.items(), key=lambda kv: kv[1])
    return lang if n >= 2 else "en"


def _count_before(text: str, end: int) -> int | None:
    window = text[max(0, end - 24) : end]
    m = _COUNT_BEFORE_UNIT.search(window)
    return to_number(m.group(1), strict=True) if m else None


def _count_term(
    pattern: re.Pattern[str],
    text: str,
    plural: re.Pattern[str] | None = None,
    distinct: re.Pattern[str] | None = None,
) -> int:
    """People a vulnerability term covers: an explicit number, a plural (2), or one.

    "6 month old baby" is one infant however many words describe it; only
    `distinct` terms ("paati", "thatha") count as separate people.
    """
    total, mentioned = 0, False
    for m in pattern.finditer(text):
        n = _count_before(text, m.start())
        if n:
            total = max(total, n)
        else:
            mentioned = True
    people = {m.group(0).lower() for m in distinct.finditer(text)} if distinct else set()
    implied = max(len(people), 2 if plural and plural.search(text) else 0, 1 if mentioned else 0)
    return max(total, implied)


def people_count(text: str) -> int | None:
    explicit: list[int] = []
    for m in _P["units"].finditer(text):
        n = _count_before(text, m.start())
        if n:
            explicit.append(n)
    for m in lx.FAMILY_OF.finditer(text):
        if n := to_number(m.group(1)):
            explicit.append(n)
    for m in lx.WE_ARE.finditer(text):
        if (n := to_number(m.group(1), strict=True)) and n <= 60:
            explicit.append(n)
    explicit += [n for word, n in lx.COLLECTIVE.items() if word in text]
    if explicit:
        return max(explicit)
    # no total given: add up the people named; "amma and appa" is one pair, not a pair and two
    pair_hits = _P["kin_pair"].findall(text)
    pairs = len(pair_hits)
    in_pairs = {w.lower() for p in pair_hits for w in p.split()}
    kin = {m.group(0).lower() for m in _P["kin"].finditer(text)} - in_pairs
    groups = 0
    for key in ("child", "elderly"):
        for m in _P[key].finditer(text):
            if n := _count_before(text, m.start()):
                groups += n
    named = len(kin) + 2 * pairs + groups
    if named and lx.SELF.search(text):
        named += 1
    return named or None


def vulnerable(text: str) -> Vulnerable:
    elderly = _count_term(_P["elderly"], text, lx.ELDERLY_PLURAL, distinct=lx.ELDERLY_KIN)
    for m in [*lx.AGE.finditer(text), *lx.AGED.finditer(text)]:
        age = int(m.group(1))
        if age >= 60 and not elderly:
            elderly = 1
    infant = _count_term(_P["infant"], text)
    if not infant and any(int(m.group(1)) <= 18 for m in lx.MONTHS_OLD.finditer(text)):
        infant = 1
    child = _count_term(_P["child"], text, lx.CHILD_PLURAL)
    for m in lx.AGE.finditer(text):
        if int(m.group(1)) < 12 and not child:
            child = 1
    if infant and child <= infant:
        child = 0  # "kai kuzhandhai" is one infant, not an infant and a child
    medical = [name for name, p in _MEDICAL.items() if p.search(text)]
    pregnant = 1 if _P["pregnant"].search(text) else 0
    if "labour" in medical:
        pregnant = max(pregnant, 1)
    return Vulnerable(
        elderly=min(elderly, 30),
        child=min(child, 50),
        infant=min(infant, 20),
        pregnant=pregnant,
        disabled=min(_count_term(_P["disabled"], text), 10),
        medical=medical,
    )


def water_level(text: str) -> str:
    best = "unknown"
    for level, p in _WATER.items():
        if p.search(text) and WATER_RANK[level] > WATER_RANK[best]:
            best = level
    depth_ft = [float(a or b) for a, b in lx.FEET.findall(text)]
    depth_ft += [float(m) * 3.28 for m in lx.METRES.findall(text) if float(m) <= 6]
    if depth_ft:
        ft = max(depth_ft)
        by_depth = (
            "neck"
            if ft >= 4.5
            else "chest"
            if ft >= 3.5
            else "waist"
            if ft >= 2.5
            else "knee"
            if ft >= 1.2
            else "ankle"
        )
        if WATER_RANK[by_depth] > WATER_RANK[best]:
            best = by_depth
    return best


def status_update(text: str) -> str:
    if _P["false_alarm"].search(text):
        return "false_alarm"
    if _P["rescued"].search(text) and not lx.NOT_RESCUED.search(text):
        return "rescued"
    return "none"


def phones(text: str) -> list[str]:
    out = []
    for mobile, landline in lx.PHONE.findall(text):
        digits = re.sub(r"\D", "", mobile or landline)
        if digits and digits not in out:
            out.append(digits)
    return out


def redact_phones(text: str) -> str:
    counter = iter(range(1, 100))
    return lx.PHONE.sub(lambda _m: f"[PHONE_{next(counter)}]", text)


def location_spans(text: str) -> tuple[str | None, str | None]:
    """(location_text, address): place-like spans, kept only if they look like places."""
    address = None
    if m := lx.ADDRESS.search(text):
        address = m.group(0).strip(" ,")
    spans: list[str] = []
    for m in lx.LOCATION_CUES.finditer(text):
        span = m.group(1).strip()
        strong = lx.STRONG_CUES.match(m.group(0))
        if strong or re.search(r"[A-Z]|\d", span) or lx.PLACE_SUFFIX.search(span):
            spans.append(span)
    spans += [m.group(1) for m in lx.PLACE_SUFFIX.finditer(text)]
    spans += [m.group(1) for m in lx.INDIC_CUES.finditer(text)]
    seen: list[str] = []
    for s in spans:
        s = lx.SPAN_STOP.sub("", re.sub(r"\s+", " ", s)).strip(" ,-")
        if s and not any(s.lower() in t.lower() for t in seen):
            seen = [t for t in seen if t.lower() not in s.lower()] + [s]
    location = ", ".join(seen[:4]) if seen else None
    if location and len(location) > 200:
        location = location[:200]
    return location, address


def contact_name(text: str) -> str | None:
    m = lx.NAME_PATTERNS.search(text)
    return m.group(1) if m else None


def needs(text: str, level: str) -> list[str]:
    found = [name for name, p in _NEEDS.items() if p.search(text)]
    if lx.NO_RESCUE.search(text):
        found = [n for n in found if n not in ("rescue", "evacuation", "boat")]
        return found or ["information"]
    if WATER_RANK[level] >= WATER_RANK["knee"] and "rescue" not in found:
        found.insert(0, "rescue")
    return found or ["rescue"]


WATER_PHRASE = {
    "ankle": "ankle-deep water",
    "knee": "knee-deep water",
    "waist": "waist-deep water",
    "chest": "chest-deep water",
    "neck": "neck-deep water",
    "first_floor": "ground floor flooded",
    "second_floor": "sheltering on 2nd floor",
    "roof": "on the roof",
    "none": "no flooding",
}
NEED_PHRASE = {
    "food": "food",
    "water": "drinking water",
    "power": "phone charge",
    "medical": "medical help",
    "information": "news of family",
}


def summarize(e: SosExtraction) -> str:
    """Who is there and what is wrong, in one line a coordinator reads at a glance."""
    v = e.vulnerable
    parts = [f"{e.people_count} people" if e.people_count else "Headcount unknown"]
    tags = [
        label
        for n, label in (
            (v.infant, f"{v.infant} infant" + ("s" if v.infant > 1 else "")),
            (v.pregnant, "pregnant woman"),
            (v.elderly, f"{v.elderly} elderly"),
            (v.child, f"{v.child} child" + ("ren" if v.child > 1 else "")),
            (v.disabled, f"{v.disabled} disabled"),
        )
        if n
    ]
    if tags:
        parts.append(", ".join(tags))
    if v.medical:
        parts.append(", ".join(m.replace("_", " ") for m in v.medical))
    if e.water_level in WATER_PHRASE:
        parts.append(WATER_PHRASE[e.water_level] + (", rising" if e.water_rising else ""))
    extra = [NEED_PHRASE[n] for n in e.needs if n in NEED_PHRASE]
    if extra:
        parts.append("needs " + ", ".join(extra))
    if e.status_update != "none":
        parts.insert(0, f"Update: {e.status_update.replace('_', ' ')}")
    return " · ".join(parts)


def extract(raw: str) -> tuple[SosExtraction, list[str]]:
    text = normalize(raw)
    level = water_level(text)
    location, address = location_spans(text)
    e = SosExtraction(
        people_count=people_count(text),
        vulnerable=vulnerable(text),
        location_text=location,
        address=address,
        water_level=level,  # type: ignore[arg-type]
        water_rising=True if _P["rising"].search(text) else None,
        needs=needs(text, level),  # type: ignore[arg-type]
        language=detect_language(text),  # type: ignore[arg-type]
        contact_name=contact_name(text),
        status_update=status_update(text),  # type: ignore[arg-type]
    )
    found = sum((e.people_count is not None, e.location_text is not None, e.water_level != "unknown"))
    e.confidence = round(0.35 + 0.15 * found, 2)
    e.summary = summarize(e)
    return e, phones(text)
