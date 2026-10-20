"""Text keys that make "Velacheri", "Velachery" and "வேளச்சேரி" compare equal.

Indic scripts share one Unicode layout (each block mirrors Devanagari), so a
single table transliterates Tamil, Hindi, Malayalam and Telugu to rough Latin.
"""

from __future__ import annotations

import re
import unicodedata

_BLOCKS = {"ta": 0x0B80, "hi": 0x0900, "ml": 0x0D00, "te": 0x0C00}

# offset within an Indic block -> Latin
_CONSONANTS = {
    0x15: "k",
    0x16: "kh",
    0x17: "g",
    0x18: "gh",
    0x19: "ng",
    0x1A: "ch",
    0x1B: "chh",
    0x1C: "j",
    0x1D: "jh",
    0x1E: "ny",
    0x1F: "t",
    0x20: "th",
    0x21: "d",
    0x22: "dh",
    0x23: "n",
    0x24: "th",
    0x25: "th",
    0x26: "d",
    0x27: "dh",
    0x28: "n",
    0x29: "n",
    0x2A: "p",
    0x2B: "ph",
    0x2C: "b",
    0x2D: "bh",
    0x2E: "m",
    0x2F: "y",
    0x30: "r",
    0x31: "r",
    0x32: "l",
    0x33: "l",
    0x34: "zh",
    0x35: "v",
    0x36: "sh",
    0x37: "sh",
    0x38: "s",
    0x39: "h",
}
_VOWELS = {
    0x05: "a",
    0x06: "aa",
    0x07: "i",
    0x08: "ii",
    0x09: "u",
    0x0A: "uu",
    0x0B: "ri",
    0x0E: "e",
    0x0F: "e",
    0x10: "ai",
    0x12: "o",
    0x13: "o",
    0x14: "au",
}
_SIGNS = {
    0x3E: "aa",
    0x3F: "i",
    0x40: "ii",
    0x41: "u",
    0x42: "uu",
    0x43: "ri",
    0x46: "e",
    0x47: "e",
    0x48: "ai",
    0x4A: "o",
    0x4B: "o",
    0x4C: "au",
}
_VIRAMA, _ANUSVARA, _VISARGA, _CANDRABINDU = 0x4D, 0x02, 0x03, 0x01
# Tamil writes k/g, t/d, p/b with one letter; voicing depends on neighbours
_TAMIL_VOICE = {"k": "g", "t": "d", "th": "d", "p": "b", "ch": "s"}


def _offset(ch: str) -> tuple[str, int] | None:
    cp = ord(ch)
    for lang, base in _BLOCKS.items():
        if base <= cp < base + 0x80:
            return lang, cp - base
    return None


def latinize(text: str) -> str:
    """Approximate Latin for Indic-script text; Latin passes through unchanged."""
    out: list[str] = []
    i, n = 0, len(text)
    dead: int | None = None  # consonant just silenced by a virama, to spot doubled letters
    while i < n:
        info = _offset(text[i])
        if info is None:
            out.append(text[i])
            dead = None
            i += 1
            continue
        lang, off = info
        if off in _VOWELS:
            out.append(_VOWELS[off])
            dead = None
        elif off in _CONSONANTS:
            cons = _CONSONANTS[off]
            nxt = _offset(text[i + 1]) if i + 1 < n else None
            nxt_off = nxt[1] if nxt else None
            if lang == "ta" and cons in _TAMIL_VOICE:
                tail = dead == off
                head = nxt_off == _VIRAMA and i + 2 < n and _offset(text[i + 2]) == (lang, off)
                prev = out[-1] if out else ""
                soft = bool(prev) and prev[-1] in "aeioumn"
                if tail:
                    cons = ""  # "ச்ச" is one "ch", not two
                elif soft and not head:
                    cons = _TAMIL_VOICE[cons]
            out.append(cons)
            dead = None
            if nxt_off in _SIGNS:
                out.append(_SIGNS[nxt_off])
                i += 1
            elif nxt_off == _VIRAMA:
                dead = off
                i += 1
            elif lang == "hi" and nxt is None:
                pass  # Hindi drops a word-final inherent vowel: "मुदिचूर" is "mudichur"
            else:
                out.append("a")
        elif off in (_ANUSVARA, _CANDRABINDU):
            out.append("n")
            dead = None
        elif off == _VISARGA:
            out.append("h")
            dead = None
        elif 0x66 <= off <= 0x6F:
            out.append(str(off - 0x66))
            dead = None
        i += 1
    return "".join(out)


# synonyms collapse to one canonical token before keys are built
_SYNONYMS: list[tuple[str, str]] = [
    # deities, so "Pillaiyar Kovil" finds "Sri Vinayagar Temple"
    (r"ganesha?|ganapath?(?:y|i)|vinaya(?:ga|ka)r?|pill?ai?yar|vigneshwara", "ganesh"),
    (r"murugan|subramani?y?a(?:swamy|r)?|subramanya|karthikeyan|kandaswamy|velan|kumaran", "murugan"),
    (r"(?:mari|muthu|kali|bhagavathi|angala|nagathamman|ellai|pidari)?amman|durga|kaliamman|mariyamman", "amman"),
    (r"perumal|vishnu|venkatesh?wara|balaji|srinivasa|narayana|ranganatha", "perumal"),
    (r"shiva|sivan|siva|easwar(?:ar|an)?|eeswarar|ishwar|kapaleeswarar", "shiva"),
    (r"hanuman|anjaneya(?:r)?|anjaneyar", "hanuman"),
    (r"ayyapp?a(?:n)?|sabari", "ayyappan"),
    (r"annai|velankanni|mother mary|our lady|madha|matha", "mary"),
    (r"sai ?baba|sai", "sai"),
    # landmark types
    (r"koil|kovil|koyil|mandir|gudi|kshetram|alayam|devasthanam", "temple"),
    (r"masjid|pallivasal|dargah|juma", "mosque"),
    (r"chapel|cathedral|parish|ch\.", "church"),
    (r"bus (?:depot|terminus|stand|station)|mtc (?:depot|terminus)|bus terminal", "busdepot"),
    (r"petrol (?:bunk|pump|station)|fuel station|bunk", "fuel"),
    (r"railway station|rly station|train station|mrts(?: station)?|metro station|metro", "station"),
    (r"eri|lake|tank|kulam|kere", "lake"),
    (r"flyover|paalam|subway|over ?bridge", "bridge"),
    (r"nursing home|hospitals|clinic|govt hospital|gh", "hospital"),
    (r"schools?|matriculation|matric|higher secondary|hr sec|hss", "school"),
    (r"apartments?|flats|towers|residency|enclave", "apartments"),
    (r"santhai|bazaa?r|markets?", "market"),
    (r"police station|ps|police", "police"),
    # street words
    (r"st\.?|str|streat", "street"),
    (r"rd\.?|salai", "road"),
    (r"nagar|ngr", "nagar"),
    (r"main road|main rd", "mainroad"),
    (r"first", "1"),
    (r"second", "2"),
    (r"third", "3"),
    (r"fourth", "4"),
    (r"fifth", "5"),
]
# one alternation, one pass: per-synonym subs made indexing 22k names take seconds
_SYN_RE = re.compile("|".join(rf"(?P<g{i}>\b(?:{a})\b)" for i, (a, _) in enumerate(_SYNONYMS)))
_SYN_OUT = {f"g{i}": b for i, (_, b) in enumerate(_SYNONYMS)}
_ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b")
_FILLER = re.compile(r"\b(?:sri|shri|sree|arulmigu|arul ?migu|the|of|new|old|thiru)\b")

# deity tokens: "Ganesh temple" names a kind of place, not one place
_DEITY_WORDS = {"ganesh", "murugan", "amman", "perumal", "shiva", "hanuman", "ayyappan", "mary", "sai"}

# words that never identify a place on their own
_GENERIC_WORDS = {
    "temple",
    "mosque",
    "church",
    "busdepot",
    "fuel",
    "station",
    "lake",
    "bridge",
    "hospital",
    "school",
    "apartments",
    "market",
    "police",
    "street",
    "road",
    "nagar",
    "mainroad",
    "bus",
    "stop",
    "park",
    "college",
    "colony",
    "near",
    "main",
    "cross",
    "lane",
    "avenue",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "chennai",
    "madras",
    "tamil",
    "nadu",
    "india",
    "post",
    "office",
    "bank",
    "signal",
    "junction",
    "extension",
    "layout",
    "block",
    "phase",
    "sector",
}


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = latinize(text)
    text = re.sub(r"[^\w\s/]", " ", text)
    text = re.sub(r"([aiu])\1+", r"\1", text)  # "pillaiyaar" spells like "pillaiyar"
    text = _ORDINAL.sub(r"\1", text)
    text = _SYN_RE.sub(lambda m: _SYN_OUT[m.lastgroup or ""], text)
    text = _FILLER.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


_PHON = [
    (r"aa+", "a"),
    (r"ee+", "i"),
    (r"ii+", "i"),
    (r"oo+", "u"),
    (r"uu+", "u"),
    (r"th", "t"),
    # Tamil has one letter for ch and s, so both sides key them as s
    (r"dh", "d"),
    (r"zh", "l"),
    (r"sh", "s"),
    (r"chh", "s"),
    (r"ch", "s"),
    (r"ph", "f"),
    (r"bh", "b"),
    (r"kh", "k"),
    (r"gh", "g"),
    (r"w", "v"),
    (r"z", "s"),
    (r"y\b", "i"),
    (r"ey\b", "i"),
    (r"q", "k"),
    (r"x", "ks"),
    (r"([a-z])\1+", r"\1"),
    (r"h\b", ""),
]
_PHON_RE = [(re.compile(a), b) for a, b in _PHON]


def phonetic(token_text: str) -> str:
    """A spelling-insensitive key for already-cleaned text."""
    s = token_text
    for pat, rep in _PHON_RE:
        s = pat.sub(rep, s)
    return s


# compared against keys, so they are keys too ("street" keys to "strit")
GENERIC = frozenset(phonetic(w) for w in _GENERIC_WORDS)
DEITIES = frozenset(phonetic(w) for w in _DEITY_WORDS)


def key(text: str) -> str:
    return phonetic(clean(text))


def tokens(text: str) -> list[str]:
    return key(text).split()


# Tamil, Malayalam and Telugu glue case endings onto names: "Velachery-yil" = "in Velachery"
_SUFFIXES = (
    "ilirundu",
    "ilirunt",
    "ukula",
    "kita",
    "kite",
    "ukku",
    "ulo",
    "uku",
    "unu",
    "yil",
    "ile",
    "kku",
    "il",
    "la",
    "le",
    "ku",
    "lo",
    "ki",
    "nu",
    "ai",
    "in",
)


def stems(token: str) -> list[str]:
    """The token and its likely bare forms, longest suffix first."""
    out = [token]
    for suf in _SUFFIXES:
        if token.endswith(suf) and len(token) - len(suf) >= 4:
            out.append(token[: -len(suf)])
    return out
