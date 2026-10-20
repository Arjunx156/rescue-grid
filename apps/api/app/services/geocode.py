"""Turn "behind the Pillaiyar kovil near Velachery bus depot" into a point and a confidence.

Evidence comes from the OSM gazetteer: localities anchor the search, named
landmarks pin it, typed phrases ("Ganesh temple", "bus depot") and streets are
resolved near the anchor. Confidence says how much a human should trust it;
below the review threshold a coordinator confirms the pin.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from rapidfuzz import fuzz, process
from shapely.geometry import shape

from app.services import textnorm

EARTH_M = 6_371_000.0
ANCHOR_RADIUS_M = 2_800.0
AGREE_M = 600.0
MAX_NGRAM = 6

KIND_WEIGHT = {"landmark": 0.55, "typed": 0.4, "street": 0.3, "place": 0.2}
# suburbs anchor better than the many "Lakshmi Nagar"s a city has
BROAD_PLACES = {"place:suburb", "place:town", "place:village", "place:admin"}
POINT_PRECISION = {"landmark": 4, "typed": 3, "street": 2, "place": 1, "pin": 5}

_TYPES = {
    "temple": "temple",
    "church": "church",
    "mosque": "mosque",
    "busdepot": "busdepot",
    "school": "school",
    "college": "college",
    "hospital": "hospital",
    "station": "station",
    "lake": "lake",
    "bridge": "bridge",
    "park": "park",
    "fuel": "fuel",
    "police": "police",
    "market": "market",
    "apartments": "apartments",
    "stop": "busstop",
}
TYPE_WORDS = {textnorm.key(w): kind for w, kind in _TYPES.items()}
STREET_WORDS = {textnorm.key(w) for w in ("street", "road", "main road", "cross", "avenue", "lane")}
NOT_QUALIFIERS = {
    textnorm.key(w) for w in ("near", "behind", "opposite", "next", "to", "beside", "at", "in", "on", "and", "back")
}
TYPE_WORDS_REV = {kind: k for k, kind in TYPE_WORDS.items()}
_NOT_A_NAME = textnorm.GENERIC | textnorm.DEITIES


def haversine_m(lat1: Any, lng1: Any, lat2: Any, lng2: Any) -> Any:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lng2) - np.asarray(lng1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_M * np.arcsin(np.sqrt(a))


def _kind(category: str, key: str) -> str:
    toks = set(key.split())
    if category.startswith("place:"):
        return "place"
    if category == "street":
        return "street"
    if category in ("amenity:place_of_worship", "building:temple", "building:church", "building:mosque"):
        if TYPE_WORDS_REV["church"] in toks or category == "building:church":
            return "church"
        if TYPE_WORDS_REV["mosque"] in toks or category == "building:mosque":
            return "mosque"
        return "temple"
    table = {
        "amenity:bus_station": "busdepot",
        "amenity:school": "school",
        "building:school": "school",
        "amenity:kindergarten": "school",
        "amenity:college": "college",
        "amenity:university": "college",
        "amenity:hospital": "hospital",
        "amenity:clinic": "hospital",
        "building:hospital": "hospital",
        "railway:station": "station",
        "railway:halt": "station",
        "public_transport:station": "station",
        "water:lake": "lake",
        "bridge:yes": "bridge",
        "man_made:bridge": "bridge",
        "leisure:park": "park",
        "leisure:playground": "park",
        "amenity:fuel": "fuel",
        "amenity:police": "police",
        "amenity:marketplace": "market",
        "shop:supermarket": "market",
        "shop:mall": "market",
        "shop:department_store": "market",
        "building:apartments": "apartments",
        "building:residential": "apartments",
    }
    if category == "highway:bus_stop":
        return "busdepot" if TYPE_WORDS_REV["busdepot"] in toks else "busstop"
    return table.get(category, "other")


@dataclass(frozen=True)
class Entry:
    name: str
    category: str
    kind: str
    lat: float
    lng: float
    key: str


@dataclass
class Candidate:
    lat: float
    lng: float
    label: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "lat": round(self.lat, 6),
            "lng": round(self.lng, 6),
            "label": self.label,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class GeoResult:
    lat: float
    lng: float
    confidence: float
    source: str
    label: str
    matched: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    locality: str | None = None
    # gazetteer entries (not localities) the point rests on; two reports sharing one describe one place
    anchors: list[str] = field(default_factory=list)


@dataclass
class _Group:
    """Every gazetteer entry that one phrase in the message could mean."""

    phrase: str
    kind: str
    idx: list[int]
    fuzzy: bool = False


class Gazetteer:
    def __init__(self, rows: list[dict[str, Any]]):
        self.entries: list[Entry] = []
        self.by_key: dict[str, list[int]] = defaultdict(list)
        self.streets: dict[str, list[int]] = defaultdict(list)  # "3 mainroad" lives in many suburbs
        for row in rows:
            names = [row["name"], *row.get("aliases", [])]
            primary_key = textnorm.key(row["name"])
            if not primary_key:
                continue
            entry = Entry(
                row["name"], row["category"], _kind(row["category"], primary_key), row["lat"], row["lng"], primary_key
            )
            i = len(self.entries)
            self.entries.append(entry)
            if entry.kind == "street":
                self.streets[primary_key].append(i)
            for name in names:
                k = textnorm.key(name)
                if k and not set(k.split()) <= _NOT_A_NAME and i not in self.by_key[k]:
                    self.by_key[k].append(i)
        self.lat = np.array([e.lat for e in self.entries])
        self.lng = np.array([e.lng for e in self.entries])
        self.kinds = np.array([e.kind for e in self.entries])
        self.place_keys = sorted({e.key for e in self.entries if e.kind == "place" and len(e.key) >= 5})
        self.keys_arr = np.array([e.key for e in self.entries], dtype=object)

    @classmethod
    def from_files(cls, landmarks: Path, water: Path | None = None) -> Gazetteer:
        rows = json.loads(landmarks.read_text(encoding="utf-8"))
        if water and water.exists():
            for f in json.loads(water.read_text(encoding="utf-8"))["features"]:
                name = f["properties"].get("name")
                if name and f["geometry"]["type"] in ("Polygon", "MultiPolygon"):
                    c = shape(f["geometry"]).representative_point()
                    rows.append({"name": name, "category": "water:lake", "lat": c.y, "lng": c.x})
        return cls(rows)

    # --- matching ----------------------------------------------------------

    def _groups(self, toks: list[str]) -> list[_Group]:
        groups: dict[str, _Group] = {}
        n = len(toks)
        covered_place: set[int] = set()
        for size in range(min(MAX_NGRAM, n), 0, -1):
            for start in range(n - size + 1):
                phrase = " ".join(toks[start : start + size])
                hits = self.by_key.get(phrase)
                if not hits or phrase in groups:
                    continue
                kinds = {self.entries[i].kind for i in hits}
                kind = "place" if kinds == {"place"} else "street" if kinds <= {"street", "place"} else "landmark"
                if kind == "landmark" and len(hits) > 1:
                    # a name shared by places and buildings ("Velachery" police) is a place
                    place_hits = [i for i in hits if self.entries[i].kind == "place"]
                    if place_hits:
                        hits, kind = place_hits, "place"
                groups[phrase] = _Group(phrase, kind, hits)
                if kind == "place":
                    covered_place.update(range(start, start + size))
        # case endings ("velaseriyil") and misspellings ("Mudichoor") on locality names
        for start, tok in enumerate(toks):
            if start in covered_place or len(tok) < 6:
                continue
            for stem in textnorm.stems(tok)[1:]:
                hits = [i for i in self.by_key.get(stem, []) if self.entries[i].kind == "place"]
                if hits and stem not in groups:
                    groups[stem] = _Group(stem, "place", hits)
                    covered_place.add(start)
                    break
        for size in (1, 2, 3):
            for start in range(n - size + 1):
                if covered_place & set(range(start, start + size)):
                    continue
                phrase = " ".join(toks[start : start + size])
                if len(phrase) < 5 or set(phrase.split()) & _NOT_A_NAME:
                    continue
                match = process.extractOne(phrase, self.place_keys, scorer=fuzz.ratio, score_cutoff=86)
                if match and match[0] not in groups:
                    hits = [i for i in self.by_key[match[0]] if self.entries[i].kind == "place"]
                    if hits:
                        groups[match[0]] = _Group(match[0], "place", hits, fuzzy=True)
        return list(groups.values())

    def _typed(self, toks: list[str]) -> list[tuple[str, list[str]]]:
        """("temple", ["ganes"]) for "...ganes temple...": a type word plus up to two qualifiers.

        Streets come back as ("street", [full phrase candidates]) such as ["4 cros", "cros"].
        """
        out: list[tuple[str, list[str]]] = []
        for i, t in enumerate(toks):
            if t in STREET_WORDS:
                lead = [q for q in toks[max(0, i - 3) : i] if q not in NOT_QUALIFIERS]
                phrases = [" ".join([*lead[k:], t]) for k in range(len(lead))]
                if phrases:
                    out.append(("street", phrases))
                continue
            kind = TYPE_WORDS.get(t)
            if not kind or (t == "stop" and (i == 0 or toks[i - 1] != "bus")):
                continue
            quals = [q for q in toks[max(0, i - 2) : i] if q not in textnorm.GENERIC and len(q) > 2]
            out.append((kind, quals))
        return out

    def _street_near(self, phrases: list[str], lat: float, lng: float) -> tuple[list[int], list[float]]:
        for phrase in phrases:  # longest first: "gandi nagar 4 street" before "4 street"
            idx = self.streets.get(phrase)
            if not idx:
                continue
            d = haversine_m(lat, lng, self.lat[idx], self.lng[idx])
            near = [(int(i), float(x)) for i, x in zip(idx, d, strict=True) if x <= ANCHOR_RADIUS_M]
            if near:
                return [i for i, _ in near], [x for _, x in near]
        return [], []

    def _nearest(self, idx: list[int] | np.ndarray, lat: float, lng: float) -> tuple[int, float]:
        idx = np.asarray(idx)
        d = haversine_m(lat, lng, self.lat[idx], self.lng[idx])
        j = int(np.argmin(d))
        return int(idx[j]), float(d[j])

    def _ambiguous_near(self, idx: list[int], lat: float, lng: float, radius: float) -> bool:
        """More than one same-named place near the anchor, far enough apart to matter."""
        if len(idx) < 2:
            return False
        arr = np.asarray(idx)
        near = arr[haversine_m(lat, lng, self.lat[arr], self.lng[arr]) <= radius]
        if len(near) < 2:
            return False
        spread = haversine_m(
            self.lat[near][:, None], self.lng[near][:, None], self.lat[near][None, :], self.lng[near][None, :]
        )
        return bool(spread.max() > 400)

    def _typed_near(self, kind: str, quals: list[str], lat: float, lng: float) -> tuple[list[int], list[float]]:
        mask = self.kinds == kind
        idx = np.nonzero(mask)[0]
        if not len(idx):
            return [], []
        d = haversine_m(lat, lng, self.lat[idx], self.lng[idx])
        near = idx[d <= ANCHOR_RADIUS_M]
        dists = d[d <= ANCHOR_RADIUS_M]
        if quals:
            keep = [j for j, i in enumerate(near) if any(q in self.entries[i].key.split() for q in quals)]
            if keep:
                return [int(near[j]) for j in keep], [float(dists[j]) for j in keep]
        return [int(i) for i in near], [float(x) for x in dists]

    # --- resolution --------------------------------------------------------

    def geocode(
        self, text: str, hints: list[str] | None = None, bias: tuple[float, float] | None = None
    ) -> GeoResult | None:
        toks = textnorm.tokens(" ".join([text, *(hints or [])]))
        if not toks:
            return None
        groups = self._groups(toks)
        typed = self._typed(toks)
        if bias:
            for g in groups:
                d = haversine_m(bias[0], bias[1], self.lat[g.idx], self.lng[g.idx])
                g.idx = [i for i, dist in zip(g.idx, d, strict=True) if dist < 45_000] or g.idx
        places = [g for g in groups if g.kind == "place"]
        specific = [g for g in groups if g.kind == "landmark" and len(g.idx) <= 3]
        anchor_groups = places or specific
        if not anchor_groups:
            return None

        scored: list[tuple[float, int, list[tuple[str, int, float]], list[str]]] = []
        for ag in anchor_groups:
            for a in ag.idx:
                lat, lng = self.entries[a].lat, self.entries[a].lng
                support: list[tuple[str, int, float]] = [(ag.kind, a, 0.0)]
                matched = [self._label(a, ag)]
                score = KIND_WEIGHT[ag.kind] * (0.7 if ag.fuzzy else 1.0)
                if ag.kind == "place":
                    broad = self.entries[a].category in BROAD_PLACES
                    score *= (1.25 if broad else 1.0) / len(ag.idx) ** 0.5
                for g in groups:
                    if g is ag:
                        continue
                    j, d = self._nearest(g.idx, lat, lng)
                    radius = ANCHOR_RADIUS_M * (1.6 if g.kind == "place" else 1.0)
                    if d <= radius:
                        kind = g.kind
                        if kind == "landmark" and self._ambiguous_near(g.idx, lat, lng, radius):
                            kind = "landmark?"  # three "Gandhi Road" bus stops in one suburb
                        score += KIND_WEIGHT[g.kind] * (1 - d / radius) * (0.6 if kind.endswith("?") else 1) + 0.1
                        support.append((kind, j, d))
                        matched.append(self._label(j, g))
                for kind, quals in typed:
                    if kind == "street":
                        cand, dists = self._street_near(quals, lat, lng)
                        if cand:
                            k = int(np.argmin(dists))
                            sure = len(cand) == 1
                            score += KIND_WEIGHT["street"] * (1.0 if sure else 0.6)
                            support.append(("street" if sure else "street?", cand[k], dists[k]))
                            matched.append(f"{self.entries[cand[k]].name} (street)")
                        continue
                    cand, dists = self._typed_near(kind, quals, lat, lng)
                    if cand:
                        k = int(np.argmin(dists))
                        unique = len(cand) == 1 or bool(quals and len(cand) <= 2)
                        score += KIND_WEIGHT["typed"] * (1.0 if unique else 0.6)
                        support.append(("typed" if unique else "typed?", cand[k], dists[k]))
                        matched.append(f"{self.entries[cand[k]].name} ({kind})")
                scored.append((score, a, support, matched))
        scored.sort(key=lambda s: s[0], reverse=True)
        best_score, anchor, support, matched = scored[0]
        result = self._finish(anchor, support, matched)

        # a second anchor far away with nearly the same evidence means we may be wrong
        rivals = [s for s in scored[1:] if s[0] >= best_score * 0.85]
        for s in rivals:
            far = haversine_m(result.lat, result.lng, self.entries[s[1]].lat, self.entries[s[1]].lng)
            if far > 3_000:
                result.confidence -= 0.14
                break
        seen = {(round(result.lat, 3), round(result.lng, 3))}
        for s in scored[1:]:
            alt = self._finish(s[1], s[2], s[3])
            k = (round(alt.lat, 3), round(alt.lng, 3))
            if k not in seen:
                seen.add(k)
                result.candidates.append(Candidate(alt.lat, alt.lng, alt.label, alt.confidence))
            if len(result.candidates) >= 3:
                break
        result.confidence = round(min(max(result.confidence, 0.15), 0.93), 2)
        return result

    def _label(self, i: int, g: _Group) -> str:
        e = self.entries[i]
        return f"{e.name} ({e.kind}{', fuzzy' if g.fuzzy else ''})"

    def _finish(self, anchor: int, support: list[tuple[str, int, float]], matched: list[str]) -> GeoResult:
        kinds = {k for k, _, _ in support}
        # the most precise point wins; two precise points that agree are averaged
        ranked = sorted(support, key=lambda s: POINT_PRECISION.get(s[0].rstrip("?"), 0), reverse=True)
        top = ranked[0]
        pts = [top[1]]
        for k, j, _ in ranked[1:]:
            if POINT_PRECISION.get(k.rstrip("?"), 0) >= 3:
                d = haversine_m(
                    self.entries[top[1]].lat, self.entries[top[1]].lng, self.entries[j].lat, self.entries[j].lng
                )
                if d <= AGREE_M:
                    pts.append(j)
        lat = float(np.mean([self.entries[j].lat for j in pts]))
        lng = float(np.mean([self.entries[j].lng for j in pts]))

        has_place = "place" in kinds
        # calibrated on the labelled replay: at 0.6 and above, nine in ten pins land within 300 m
        if "landmark" in kinds:
            conf = 0.84 if has_place or len(kinds) > 1 else 0.72
        elif "street" in kinds:
            conf = 0.7 if has_place else 0.4
        elif "landmark?" in kinds:
            conf = 0.55 if has_place else 0.4
        elif "typed" in kinds:
            conf = 0.58 if has_place else 0.45
        elif "typed?" in kinds:
            conf = 0.5 if has_place else 0.35
        elif "street" in kinds:
            conf = 0.7 if has_place else 0.4
        elif "street?" in kinds:
            conf = 0.58 if has_place else 0.35
        else:
            conf = 0.45
        conf += min(0.08, 0.04 * (len(pts) - 1))
        anchor_e = self.entries[anchor]
        top_e = self.entries[top[1]]
        locality = anchor_e.name if anchor_e.kind == "place" else None
        label = top_e.name if top[1] == anchor else f"{top_e.name}, {anchor_e.name}"
        anchors = sorted(
            {f"{self.entries[j].name}|{self.entries[j].kind}" for k, j, _ in support if k.rstrip("?") != "place"}
        )
        return GeoResult(lat, lng, conf, "gazetteer", label, matched, locality=locality, anchors=anchors)


@lru_cache
def gazetteer(data_dir: str) -> Gazetteer:
    base = Path(data_dir) / "geo"
    return Gazetteer.from_files(base / "landmarks.json", base / "water.geojson")


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360
