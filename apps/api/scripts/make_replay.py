"""Generate the Chennai December 2015 replay: synthetic SOS traffic with ground truth.

Real 2015 SOS sheets carry real people's phones and medical details, so the
replay is synthetic but modelled on them: real localities, landmarks and streets
from OSM inside the simulated flood (app.sim.flood); households reported by
several relatives in different languages; vague, duplicate and stale reports;
supply requests mixed in. Every message keeps its truth so the same file is both
the demo replay and the labelled evaluation set.

The water drives the story. A family sends its first SOS after the simulated
water enters the house, every report describes the depth at the moment it was
sent, and each family has a danger line (the roof for a single-storey house, the
first floor for a taller one, much lower for someone who cannot climb) and the
time the water truly crossed it.

Phone numbers start with 5, which no Indian mobile number does, so nothing in
this file can ever reach a real person.

    uv run python scripts/make_replay.py
"""

from __future__ import annotations

import json
import math
import random
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import Point, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[3] / "data"
OUT_DIR = ROOT / "replay" / "chennai-2015"
SEED = 2015
IST = timedelta(hours=5, minutes=30)
START = datetime(2015, 12, 1, 18, 0, tzinfo=UTC) - IST  # 6 pm IST, as the Chembarambakkam release grew
HOURS = 48
HOUSEHOLDS = 450

rng = random.Random(SEED)
np_rng = np.random.default_rng(SEED)

NAMES = [
    "Ramesh",
    "Suresh",
    "Lakshmi",
    "Kavitha",
    "Murugan",
    "Selvi",
    "Karthik",
    "Priya",
    "Senthil",
    "Revathi",
    "Ganesan",
    "Meena",
    "Arun",
    "Divya",
    "Balaji",
    "Saravanan",
    "Anitha",
    "Venkatesh",
    "Parvathi",
    "Raja",
    "Mohan",
    "Geetha",
    "Prakash",
    "Deepa",
    "Vijay",
    "Malathi",
    "Kumar",
    "Shanthi",
    "Ravi",
    "Uma",
    "Anand",
    "Jaya",
    "Sundar",
    "Kala",
    "Mani",
    "Vasanthi",
    "Ashok",
    "Sumathi",
    "Gopal",
    "Radha",
    "Hari",
    "Bhuvana",
    "Dinesh",
    "Nirmala",
    "Elango",
    "Padma",
    "Kannan",
    "Saroja",
    "Rajesh",
    "Usha",
    "Rahul",
    "Pooja",
    "Biju",
    "Anju",
    "Srinivas",
    "Lavanya",
    "Farook",
    "Ayesha",
    "Joseph",
    "Mary",
]
LANDMARK_KINDS = {
    "amenity:place_of_worship": "temple",
    "amenity:school": "school",
    "amenity:bus_station": "bus depot",
    "amenity:hospital": "hospital",
    "leisure:park": "park",
    "building:apartments": "apartments",
    "railway:station": "station",
    "amenity:fuel": "petrol bunk",
    "shop:supermarket": "supermarket",
    "amenity:college": "college",
    "amenity:police": "police station",
    "amenity:community_centre": "hall",
    "amenity:marriage_hall": "marriage hall",
    "amenity:bank": "bank",
}
BROAD = {"place:suburb", "place:town", "place:village", "place:admin", "place:neighbourhood"}

ENTERS_HOUSE_M = 0.45  # above the plinth: the moment families start calling for help
MIN_SPACING_M = 250.0
STOREYS = [(1, 0.45), (2, 0.4), (3, 0.15)]
CANNOT_CLIMB_MEDICAL = {"dialysis", "oxygen", "cardiac", "labour", "injury"}
MEDICAL_DIST = [
    ("dialysis", 0.03),
    ("oxygen", 0.02),
    ("cardiac", 0.03),
    ("diabetes", 0.04),
    ("labour", 0.012),
    ("injury", 0.02),
    ("cancer", 0.01),
    ("fever", 0.03),
]


# --- phrasing per language -----------------------------------------------------------------

WATER = {
    "en": {
        "ankle": ["ankle deep water inside", "street flooded, water up to our ankles"],
        "knee": ["water knee deep inside the house", "knee level water in the house"],
        "waist": ["waist deep water", "water up to waist level"],
        "chest": ["water at chest level", "chest deep water inside"],
        "first_floor": [
            "ground floor fully submerged, we moved to first floor",
            "ground floor is under water, they are on the first floor",
        ],
        "neck": ["neck deep water", "water up to neck level"],
        "roof": ["stuck on the terrace", "they are on the roof top"],
        "second_floor": ["sheltering on the second floor", "on 2nd floor, below is flooded"],
    },
    "tg": {
        "ankle": ["street flooded, kanukkal varaikum thanni"],
        "knee": ["mutti varaikum thanni"],
        "waist": ["idupu varaikum thanni"],
        "chest": ["nenju varaikum thanni"],
        "neck": ["kazhuthu varaikum thanni"],
        "first_floor": ["ground floor full ah moozhgiduchu, first floor la irukkom"],
        "roof": ["mottai maadi la irukkom"],
        "second_floor": ["second floor la irukkom"],
    },
    "ta": {
        "ankle": ["கணுக்கால் வரை தண்ணீர்"],
        "knee": ["முழங்கால் வரை தண்ணீர்"],
        "waist": ["இடுப்பு வரை தண்ணீர்"],
        "chest": ["மார்பு வரை தண்ணீர்"],
        "neck": ["கழுத்து வரை தண்ணீர்"],
        "first_floor": ["தரைத்தளம் மூழ்கியது, முதல் மாடியில் இருக்கிறோம்"],
        "roof": ["மொட்டை மாடியில் இருக்கிறோம்"],
        "second_floor": ["இரண்டாவது மாடியில் இருக்கிறோம்"],
    },
    "hi": {
        "ankle": ["टखने तक पानी"],
        "knee": ["घुटनों तक पानी"],
        "waist": ["कमर तक पानी"],
        "chest": ["सीने तक पानी"],
        "neck": ["गले तक पानी"],
        "first_floor": ["नीचे सब डूब गया, पहली मंजिल पर हैं"],
        "roof": ["छत पर हैं"],
        "second_floor": ["दूसरी मंजिल पर हैं"],
    },
    "ml": {
        "ankle": ["കണങ്കാൽ വരെ വെള്ളം"],
        "knee": ["മുട്ടോളം വെള്ളം"],
        "waist": ["അരയോളം വെള്ളം"],
        "chest": ["നെഞ്ചോളം വെള്ളം"],
        "neck": ["കഴുത്തോളം വെള്ളം"],
        "first_floor": ["ഒന്നാം നിലയിലാണ്, താഴെ മുഴുവൻ വെള്ളം"],
        "roof": ["ടെറസിലാണ്"],
        "second_floor": ["രണ്ടാം നിലയിലാണ്"],
    },
    "te": {
        "ankle": ["చీలమండ వరకు నీరు"],
        "knee": ["మోకాళ్ళ వరకు నీరు"],
        "waist": ["నడుము వరకు నీరు"],
        "chest": ["ఛాతీ వరకు నీరు"],
        "neck": ["మెడ వరకు నీరు"],
        "first_floor": ["కింద మునిగిపోయింది, మొదటి అంతస్తులో ఉన్నాము"],
        "roof": ["డాబా మీద ఉన్నాము"],
        "second_floor": ["రెండవ అంతస్తులో ఉన్నాము"],
    },
}
RISING = {
    "en": ["Water still rising.", "Level increasing fast."],
    "tg": ["thanni eri kitte irukku."],
    "ta": ["தண்ணீர் ஏறிக்கொண்டே இருக்கிறது."],
    "hi": ["पानी बढ़ रहा है।"],
    "ml": ["വെള്ളം ഉയരുന്നു."],
    "te": ["నీరు పెరుగుతోంది."],
}

VULN = {  # (key) -> language -> phrases; "{k}" is a count
    "elderly": {
        "en": ["{k} elderly", "{k} senior citizens"],
        "tg": ["{k} vayasanavanga"],
        "ta": ["{k} முதியவர்கள்"],
        "hi": ["{k} बुजुर्ग"],
        "ml": ["{k} പ്രായമായവർ"],
        "te": ["{k} వృద్ధులు"],
    },
    "elderly1": {
        "en": ["an elderly grandmother", "my 78 year old grandfather", "an old lady"],
        "tg": ["paati irukkanga", "vayasana thatha irukkanga"],
        "ta": ["பாட்டி உள்ளார்"],
        "hi": ["बुजुर्ग दादी हैं"],
        "ml": ["പ്രായമായ അമ്മൂമ്മയുണ്ട്"],
        "te": ["అమ్మమ్మ ఉంది"],
    },
    "child": {
        "en": ["{k} kids", "{k} children"],
        "tg": ["{k} kuzhandhainga"],
        "ta": ["{k} குழந்தைகள்"],
        "hi": ["{k} बच्चे"],
        "ml": ["{k} കുട്ടികൾ"],
        "te": ["{k} పిల్లలు"],
    },
    "child1": {
        "en": ["a small child", "one kid"],
        "tg": ["oru kuzhandhai"],
        "ta": ["ஒரு குழந்தை"],
        "hi": ["एक बच्चा"],
        "ml": ["ഒരു കുട്ടി"],
        "te": ["ఒక చిన్నారి"],
    },
    "infant": {
        "en": ["a 6 month old baby", "a newborn baby", "an infant"],
        "tg": ["kai kuzhandhai irukku"],
        "ta": ["கைக்குழந்தை உள்ளது"],
        "hi": ["एक नवजात शिशु"],
        "ml": ["കൈക്കുഞ്ഞുണ്ട്"],
        "te": ["పసిపాప ఉంది"],
    },
    "pregnant": {
        "en": ["a pregnant woman", "my sister who is 8 months pregnant"],
        "tg": ["garbini pen irukkanga"],
        "ta": ["ஒரு கர்ப்பிணி பெண் உள்ளார்"],
        "hi": ["एक गर्भवती महिला"],
        "ml": ["ഗർഭിണിയുണ്ട്"],
        "te": ["గర్భిణి ఉంది"],
    },
    "disabled": {
        "en": ["a wheelchair user", "a bedridden person", "someone who cannot walk"],
        "tg": ["nadakka mudiyadha oruthar"],
        "ta": ["நடக்க முடியாத ஒருவர்"],
        "hi": ["एक विकलांग व्यक्ति"],
        "ml": ["കിടപ്പിലായ ഒരാൾ"],
        "te": ["నడవలేని వ్యక్తి"],
    },
    "dialysis": {
        "en": ["father needs dialysis", "one dialysis patient"],
        "tg": ["appa ku dialysis"],
        "ta": ["அப்பாவுக்கு டயாலிசிஸ் தேவை"],
        "hi": ["डायलिसिस मरीज है"],
        "ml": ["ഡയാലിസിസ് രോഗിയുണ്ട്"],
        "te": ["డయాలసిస్ రోగి ఉన్నారు"],
    },
    "oxygen": {
        "en": ["mother is on oxygen support", "oxygen cylinder running out"],
        "tg": ["amma oxygen la irukkanga"],
        "ta": ["அம்மா ஆக்ஸிஜன் உதவியில் உள்ளார்"],
        "hi": ["माँ ऑक्सीजन पर हैं"],
        "ml": ["ഓക്സിജൻ വേണം"],
        "te": ["ఆక్సిజన్ అవసరం"],
    },
    "cardiac": {
        "en": ["a heart patient", "uncle had a heart attack last month"],
        "tg": ["heart patient irukkanga"],
        "ta": ["இதய நோயாளி உள்ளார்"],
        "hi": ["दिल के मरीज हैं"],
        "ml": ["ഹൃദയ രോഗിയുണ്ട്"],
        "te": ["గుండె జబ్బు రోగి ఉన్నారు"],
    },
    "diabetes": {
        "en": ["diabetic, insulin running out"],
        "tg": ["sugar patient, insulin illa"],
        "ta": ["சர்க்கரை நோயாளி, இன்சுலின் தேவை"],
        "hi": ["शुगर के मरीज, इंसुलिन चाहिए"],
        "ml": ["പ്രമേഹ രോഗി, ഇൻസുലിൻ വേണം"],
        "te": ["షుగర్ రోగి, ఇన్సులిన్ కావాలి"],
    },
    "labour": {
        "en": ["wife is in labour pain"],
        "tg": ["manaivi ku prasava vali"],
        "ta": ["மனைவிக்கு பிரசவ வலி"],
        "hi": ["पत्नी को प्रसव पीड़ा"],
        "ml": ["പ്രസവ വേദന"],
        "te": ["ప్రసవ నొప్పి"],
    },
    "injury": {
        "en": ["one person injured and bleeding"],
        "tg": ["oruthar ku adipattu ratham varudhu injured"],
        "ta": ["ஒருவருக்கு காயம், ரத்தம் வருகிறது"],
        "hi": ["एक व्यक्ति घायल है"],
        "ml": ["ഒരാൾക്ക് പരിക്ക്"],
        "te": ["ఒకరికి గాయం"],
    },
    "cancer": {
        "en": ["a cancer patient on chemo"],
        "tg": ["cancer patient irukkanga"],
        "ta": ["புற்றுநோயாளி உள்ளார்"],
        "hi": ["कैंसर मरीज है"],
        "ml": ["കാൻസർ രോഗിയുണ്ട്"],
        "te": ["క్యాన్సర్ రోగి ఉన్నారు"],
    },
    "fever": {
        "en": ["high fever since morning"],
        "tg": ["kaichal irukku"],
        "ta": ["காய்ச்சல் உள்ளது"],
        "hi": ["बुखार है"],
        "ml": ["പനിയുണ്ട്"],
        "te": ["జ్వరం ఉంది"],
    },
}
NEAR = {
    "en": ["near {lm}", "behind {lm}", "opposite {lm}", "next to {lm}", "close to {lm}"],
    "tg": ["{lm} pakkathula", "{lm} kitta"],
    "ta": ["{lm} அருகில்", "{lm} பின்னால்"],
    "hi": ["{lm} के पास"],
    "ml": ["{lm} അടുത്ത്"],
    "te": ["{lm} దగ్గర"],
}

TEMPLATES = {
    "en": [
        "SOS!! {who} stuck {place}, {loc}. {water}. {vuln} {rising} Please send boat. Contact {name} {phone}",
        "Urgent help needed - {place}, {loc}. {who} trapped. {vuln} {water}. Call {phone}",
        "{loc} {place} - {who} {vuln} {water} {rising} pls rescue {phone}",
        "Please share. My relatives in {loc} ({place}) are not able to come out. {who}. {water}. {vuln} Phone {phone} {name}",
        "RESCUE REQUIRED: Location - {place}, {loc}, Chennai. People - {n}. {vuln} Water level - {water}. Contact - {phone}",
        "Friends, {who} stranded {place} in {loc} since last night, {water}. {vuln} Kindly help. {phone}",
        "Need boat urgently at {loc}. {place}. {who}. {water}. {rising}",
        "Forwarded as received: {loc} - {place} - {n} people incl {vuln} - {water} - contact {name} {phone}",
    ],
    "helpline": [
        "Caller reports {n} persons at {place}, {loc}. {vuln} {water}. Callback {phone}.",
        "Helpline call: {who} at {place}, {loc}. {water}. {vuln} {rising}",
    ],
    "csv": ["{loc}; {place}; {n} ppl; {vuln} {water}; {phone}"],
    "tg": [
        "{loc} {place} la {n} peru maatikittu irukkanga, {water}, {vuln} kaapathunga pls {phone}",
        "Anna help pannunga, {loc} la {n} peru sikkikittu irukkanga {place}, {water}, {rising} {phone}",
        "Romba urgent, {loc} {place} {n} peru irukom, {vuln} boat anupunga {phone}",
    ],
    "ta": [
        "அவசரம்! {loc} {place} {n} பேர் சிக்கியுள்ளனர். {water}. {vuln} உடனே உதவுங்கள். {phone}",
        "{loc} பகுதியில் {place} எங்கள் குடும்பம் {n} பேர் வெள்ளத்தில் சிக்கியுள்ளோம். {water}. {rising} படகு அனுப்பவும். {phone}",
    ],
    "hi": [
        "मदद चाहिए! {loc} में {place} {n} लोग फंसे हैं। {water}। {vuln} कृपया नाव भेजें। {phone}",
        "Bhai help karo, {loc} mein {place} {n} log fanse hain, {water}, {vuln} {phone}",
    ],
    "ml": ["സഹായം വേണം! {loc} {place} {n} പേർ കുടുങ്ങിയിരിക്കുന്നു. {water}. {vuln} {phone}"],
    "te": ["సహాయం కావాలి! {loc} లో {place} {n} మంది చిక్కుకున్నారు. {water}. {vuln} పడవ పంపండి. {phone}"],
}
UPDATES = {
    "en": [
        "Update: the family at {place}, {loc} has been rescued by local fishermen. Please ignore the earlier message. Thank you all",
        "They are safe now, moved to relief camp. Please ignore SOS for {loc} {place}. Contact {phone}",
    ],
    "tg": ["{loc} {place} la irundhavanga safe-a irukkanga, kaapathitanga, thanks. Ignore pannunga"],
    "ta": ["{loc} {place} சிக்கியிருந்தவர்கள் மீட்கப்பட்டனர். நன்றி"],
}
SUPPLIES = [
    "Relief camp at {lm}, {loc} needs food and drinking water for {n} people. No rescue needed",
    "{loc}: {n} families need milk and food packets at {lm}",
    "Drinking water needed urgently at {lm}, {loc} relief center, around {n} people",
]
# reporter language mix (en heavy, as in the 2015 sheets)
LANG_MIX = [("en", 0.52), ("tg", 0.16), ("ta", 0.15), ("hi", 0.07), ("ml", 0.05), ("te", 0.05)]


def speakable(name: str) -> bool:
    """Names a resident would actually say: no ward numbers, codes or long official titles."""
    return (
        len(name) <= 35
        and not re.search(r"\bward\b|\bzone\b|collective|\d{3,}|[-/()]", name, re.IGNORECASE)
        and any(c.isalpha() for c in name)
    )


def pick(weights: list[tuple[str, float]]) -> str:
    return rng.choices([k for k, _ in weights], weights=[w for _, w in weights])[0]


def fake_phone() -> str:
    digits = "5" + "".join(rng.choice("0123456789") for _ in range(9))
    style = rng.random()
    if style < 0.4:
        return f"{digits[:5]} {digits[5:]}"
    if style < 0.6:
        return f"+91 {digits}"
    return digits


def jitter(lat: float, lng: float, max_m: float) -> tuple[float, float]:
    r = max_m * math.sqrt(rng.random())
    a = rng.random() * 2 * math.pi
    return lat + r * math.cos(a) / 110_600, lng + r * math.sin(a) / 107_800


class Water:
    """The simulated flood (app.sim.flood): depth at any household, any minute from the start."""

    def __init__(self) -> None:
        terrain = np.load(ROOT / "geo" / "terrain.npz")
        water = np.load(OUT_DIR / "water.npz")
        self.west, self.north = float(terrain["bounds"][0]), float(terrain["bounds"][3])
        self.cell_m = float(terrain["cell_m"])
        self.frames = water["frames"]
        self.step_m = float(water["step_m"])
        self.minutes = np.arange(self.frames.shape[0]) * float(water["every_min"])

    def series(self, lat: float, lng: float) -> np.ndarray:
        i = int((self.north - lat) / (self.cell_m / 110_600))
        j = int((lng - self.west) / (self.cell_m / 107_800))
        return self.frames[:, i, j] * self.step_m

    def at(self, series: np.ndarray, minute: float) -> float:
        return float(np.interp(minute, self.minutes, series))

    def first_above(self, series: np.ndarray, depth: float, after: float = 0.0) -> float | None:
        hits = np.nonzero((series >= depth) & (self.minutes >= after))[0]
        return float(self.minutes[hits[0]]) if len(hits) else None


def water_word(depth: float, storeys: int) -> str:
    """What a relative would say about this depth, given where the family can go."""
    if depth < 0.25:
        return "ankle"
    if depth < 0.6:
        return "knee"
    if depth < 1.0:
        return "waist"
    if depth < 1.3:
        return "chest"
    if storeys >= 3 and depth >= 2.8:
        return "second_floor"
    if storeys >= 2:
        return "first_floor"
    return "neck" if depth < 1.9 else "roof"


def danger_line(h: dict) -> float:
    """The truth: the depth at which this family's refuge fails."""
    cannot_climb = h["disabled"] or h["infant"] or set(h["medical"]) & CANNOT_CLIMB_MEDICAL
    if h["storeys"] == 1:
        return 1.1 if cannot_climb else 2.4  # the roof is the only way up
    return 3.4  # the first floor floods


def load_geo() -> tuple[list[dict[str, Any]], list[dict[str, Any]], Any]:
    landmarks = json.loads((ROOT / "geo" / "landmarks.json").read_text(encoding="utf-8"))
    zones = json.loads((OUT_DIR / "flood_zones.geojson").read_text(encoding="utf-8"))["features"]
    return landmarks, zones, unary_union([shape(z["geometry"]) for z in zones])


def nearest(rows: list[dict[str, Any]], arr: np.ndarray, lat: float, lng: float, max_m: float) -> dict | None:
    if not len(rows):
        return None
    d = np.hypot((arr[:, 0] - lat) * 110_600, (arr[:, 1] - lng) * 107_800)
    i = int(np.argmin(d))
    return rows[i] if d[i] <= max_m else None


def ta_name(row: dict[str, Any]) -> str:
    tamil = [a for a in row.get("aliases", []) if any("஀" <= c <= "௿" for c in a)]
    return tamil[0] if tamil and rng.random() < 0.7 else row["name"]


def sample_household(i: int, idx: dict[str, Any], zones: list[dict], water: Water, taken: np.ndarray) -> dict:
    # people send SOS from deep water far more than from shallow
    weights = [shape(z["geometry"]).area * z["properties"]["depth_m"] ** 2 for z in zones]
    tries = 0
    while True:
        tries += 1
        z = rng.choices(zones, weights=weights)[0]
        g = shape(z["geometry"])
        minx, miny, maxx, maxy = g.bounds
        lng, lat = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if not g.contains(Point(lng, lat)):
            continue
        # neighbours, not the same lane: keep families apart, easing off only if the deep water fills up
        spacing = MIN_SPACING_M * max(0.4, 1 - tries / 600)
        if len(taken) and np.hypot((taken[:, 0] - lat) * 110_600, (taken[:, 1] - lng) * 107_800).min() < spacing:
            continue
        depth = water.series(lat, lng)
        enters = water.first_above(depth, ENTERS_HOUSE_M)
        if enters is None or enters > HOURS * 60 - 180:
            continue  # the water never came in, or came too late to report
        loc = nearest(idx["places"], idx["places_arr"], lat, lng, 2500)
        lm = nearest(idx["landmarks"], idx["landmarks_arr"], lat, lng, 280)
        street = nearest(idx["streets"], idx["streets_arr"], lat, lng, 220)
        if loc and (lm or street):
            break
    people = rng.choices([1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15], weights=[6, 18, 16, 20, 14, 8, 5, 4, 4, 3, 2])[0]
    elderly = min(people, rng.choice([1, 2])) if rng.random() < 0.34 else 0
    child = min(max(0, people - elderly - 1), rng.choice([1, 2, 3])) if rng.random() < 0.33 else 0
    infant = 1 if rng.random() < 0.07 and people - elderly - child >= 2 else 0
    pregnant = 1 if rng.random() < 0.05 and people >= 2 else 0
    disabled = 1 if rng.random() < 0.07 else 0
    medical = [m for m, p in MEDICAL_DIST if rng.random() < p]
    if "labour" in medical:
        pregnant = 1
    h = {
        "id": f"h{i:04d}",
        "lat": lat,
        "lng": lng,
        "zone_depth": z["properties"]["depth_m"],
        "locality": loc,
        "landmark": lm,
        "street": street,
        "door": f"{rng.randint(1, 160)}{rng.choice(['', '', '', 'A', 'B', '/2'])}",
        "people": people,
        "elderly": elderly,
        "child": child,
        "infant": infant,
        "pregnant": pregnant,
        "disabled": disabled,
        "medical": medical,
        "storeys": int(pick([(str(k), w) for k, w in STOREYS])),
        "name": rng.choice(NAMES),
        "phone": fake_phone(),
        "depth": depth,
        # people call once the water is inside; a backlog has built up by the time the replay starts
        "onset": max(enters, 0.0) + rng.expovariate(1 / (60 if enters <= 0 else 25)),
    }
    h["danger_m"] = danger_line(h)
    h["danger_min"] = water.first_above(depth, h["danger_m"], after=h["onset"])
    return h


def describe_place(h: dict, lang: str, mode: str) -> str:
    if mode == "address" and h["street"]:
        if lang in ("en", "tg"):
            return f"No. {h['door']}, {h['street']['name']}"
        return f"{h['door']}, {h['street']['name']}"
    if h["landmark"]:
        lm = ta_name(h["landmark"]) if lang == "ta" else h["landmark"]["name"]
        return rng.choice(NEAR[lang]).format(lm=lm)
    return h["street"]["name"]


def vuln_phrase(h: dict, lang: str, forget: float) -> tuple[str, dict[str, Any]]:
    """The vulnerability text and what it actually states."""
    parts, said = [], {"elderly": 0, "child": 0, "infant": 0, "pregnant": 0, "disabled": 0, "medical": []}
    for key in ("elderly", "child"):
        k = h[key]
        if k and rng.random() > forget:
            variants = VULN[key + "1"] if k == 1 else VULN[key]
            parts.append(rng.choice(variants[lang]).format(k=k))
            said[key] = k
    for key in ("infant", "pregnant", "disabled"):
        if h[key] and rng.random() > forget:
            parts.append(rng.choice(VULN[key][lang]))
            said[key] = h[key]
    for m in h["medical"]:
        if rng.random() > forget * 0.5:  # relatives rarely forget a medical condition
            parts.append(rng.choice(VULN[m][lang]))
            said["medical"].append(m)
    text = ", ".join(parts)
    return (text + ("." if lang in ("en",) and text else "")), said


def who_phrase(n: int, lang: str) -> str:
    if lang != "en":
        return f"{n}"
    if n == 1:
        return rng.choice(["1 person", "one person alone", "an old man living alone"])
    return rng.choice([f"{n} people", f"family of {n}", f"{n} members", f"we are {n}"])


def make_report(h: dict, t: datetime, water: Water, rng_lang: str | None = None) -> dict[str, Any]:
    lang = rng_lang or pick(LANG_MIX)
    channel = rng.choices(
        ["whatsapp", "web_form", "helpline", "csv_import", "twitter"], weights=[0.55, 0.15, 0.15, 0.1, 0.05]
    )[0]
    if channel in ("helpline", "csv_import"):
        lang = "en"
    mode = rng.choices(["landmark", "address", "vague"], weights=[0.58, 0.28, 0.14])[0]
    if mode == "address" and not h["street"]:
        mode = "landmark"
    loc_row = h["locality"]
    loc = ta_name(loc_row) if lang == "ta" else loc_row["name"]
    place = "" if mode == "vague" else describe_place(h, lang, mode)
    n = h["people"] if rng.random() > 0.1 else max(1, h["people"] + rng.choice([-1, 1]))
    vuln, said = vuln_phrase(h, lang, forget=0.2)
    minute = (t - START).total_seconds() / 60
    level = water_word(water.at(h["depth"], minute), h["storeys"])
    is_rising = water.at(h["depth"], minute + 30) > water.at(h["depth"], minute) + 0.05
    water_text = rng.choice(WATER[lang][level])
    rising = rng.choice(RISING[lang]) if is_rising and rng.random() < 0.8 else ""
    include_phone = rng.random() < 0.65
    include_name = rng.random() < 0.4
    key = "helpline" if channel == "helpline" else "csv" if channel == "csv_import" else lang
    template = rng.choice(TEMPLATES[key])
    if "{vuln}" not in template:  # truth must only claim what the text says
        said = {k: 0 for k in said} | {"medical": []}
    text = template.format(
        who=who_phrase(n, lang),
        n=n,
        place=place,
        loc=loc,
        water=water_text,
        vuln=vuln,
        rising=rising,
        name=h["name"] if include_name else "",
        phone=h["phone"] if include_phone else "",
    )
    text = " ".join(text.split())
    text = re.sub(r"\s*-\s*,|,\s*,|\(\)", ",", text)  # empty slots in vague reports
    text = re.sub(r"\s+([,.;।])", r"\1", text).replace(",,", ",").strip(" ,")
    if channel == "twitter":
        text = text[:260] + " #ChennaiRains #ChennaiFloods"
    if rng.random() < 0.25:
        text = text.lower()
    pin = None
    if channel == "whatsapp" and rng.random() < 0.2:
        pin = list(jitter(h["lat"], h["lng"], 25))
    stated_people = n if str(n) in text else None
    return {
        "t": t.isoformat(),
        "channel": channel,
        "text": text,
        "sender_phone": fake_phone() if channel in ("whatsapp", "helpline") else None,
        "pin": pin,
        "truth": {
            "kind": "sos",
            "household": h["id"],
            "language": "ta" if lang == "tg" else lang,
            "people": h["people"],
            "stated_people": stated_people,
            "said": said,
            "vulnerable": {k: h[k] for k in ("elderly", "child", "infant", "pregnant", "disabled")}
            | {"medical": h["medical"]},
            "water": level,
            "rising": is_rising,
            "depth_m": round(water.at(h["depth"], minute), 2),
            "lat": round(h["lat"], 6),
            "lng": round(h["lng"], 6),
            "mode": "pin" if pin else mode,
            "contact_phone_included": include_phone,
        },
    }


def pick_bases(landmarks: list[dict], flood: Any, n: int) -> list[dict]:
    """Relief bases: colleges and schools near the flood but on dry ground, spread out."""
    cands = [
        r
        for r in landmarks
        if r["category"] in ("amenity:college", "amenity:school", "amenity:university")
        and not flood.contains(Point(r["lng"], r["lat"]))
        and flood.distance(Point(r["lng"], r["lat"])) < 0.02
    ]
    chosen: list[dict] = []
    while len(chosen) < n and cands:
        if not chosen:
            best = rng.choice(cands)
        else:
            best = max(cands, key=lambda r: min(math.hypot(r["lat"] - c["lat"], r["lng"] - c["lng"]) for c in chosen))
        chosen.append(best)
        cands.remove(best)
    return chosen


def main() -> None:
    landmarks, zones, flood = load_geo()
    places = [r for r in landmarks if r["category"] in BROAD and speakable(r["name"])]
    lms = [r for r in landmarks if r["category"] in LANDMARK_KINDS and speakable(r["name"])]
    streets = [r for r in landmarks if r["category"] == "street"]
    idx = {
        "places": places,
        "places_arr": np.array([[r["lat"], r["lng"]] for r in places]),
        "landmarks": lms,
        "landmarks_arr": np.array([[r["lat"], r["lng"]] for r in lms]),
        "streets": streets,
        "streets_arr": np.array([[r["lat"], r["lng"]] for r in streets]),
    }

    water = Water()
    messages: list[dict[str, Any]] = []
    households: list[dict] = []
    for i in range(HOUSEHOLDS):
        taken = np.array([(h["lat"], h["lng"]) for h in households]).reshape(-1, 2)
        households.append(sample_household(i, idx, zones, water, taken))
    for h in households:
        t0 = START + timedelta(minutes=h["onset"])
        h["first_report"] = t0.isoformat()
        h["water"] = water_word(water.at(h["depth"], h["onset"]), h["storeys"])
        h["rising"] = water.at(h["depth"], h["onset"] + 30) > water.at(h["depth"], h["onset"]) + 0.05
        h["danger_at"] = (START + timedelta(minutes=h["danger_min"])).isoformat() if h["danger_min"] else None
        reports = rng.choices([1, 2, 3, 4, 5, 6], weights=[44, 25, 15, 8, 5, 3])[0]
        times = sorted([t0] + [t0 + timedelta(minutes=rng.expovariate(1 / 110)) for _ in range(reports - 1)])
        for t in times:
            if t < START + timedelta(hours=HOURS):
                messages.append(make_report(h, t, water))
        # some families get out on their own; a relative later says so
        if rng.random() < 0.08:
            safe_at = t0 + timedelta(minutes=rng.uniform(120, 600))
            h["self_rescued_at"] = safe_at.isoformat()
            lang = rng.choice(["en", "en", "tg", "ta"])
            loc = ta_name(h["locality"]) if lang == "ta" else h["locality"]["name"]
            text = rng.choice(UPDATES[lang]).format(
                place=describe_place(h, lang, "landmark"), loc=loc, phone=h["phone"]
            )
            sent = safe_at + timedelta(minutes=rng.uniform(20, 90))
            if sent < START + timedelta(hours=HOURS):
                messages.append(
                    {
                        "t": sent.isoformat(),
                        "channel": "whatsapp",
                        "text": text,
                        "sender_phone": fake_phone(),
                        "pin": None,
                        "truth": {
                            "kind": "update",
                            "household": h["id"],
                            "language": "ta" if lang == "tg" else lang,
                            "lat": round(h["lat"], 6),
                            "lng": round(h["lng"], 6),
                        },
                    }
                )

    # relief camps asking for supplies: real work, but not a rescue
    for _ in range(60):
        lm = rng.choice(lms)
        loc = nearest(places, idx["places_arr"], lm["lat"], lm["lng"], 3000)
        if not loc:
            continue
        text = rng.choice(SUPPLIES).format(lm=lm["name"], loc=loc["name"], n=rng.choice([40, 80, 150, 300]))
        t = START + timedelta(minutes=rng.uniform(360, HOURS * 60 - 60))
        messages.append(
            {
                "t": t.isoformat(),
                "channel": rng.choice(["whatsapp", "web_form", "twitter"]),
                "text": text,
                "sender_phone": None,
                "pin": None,
                "truth": {"kind": "supplies", "household": None, "language": "en", "lat": lm["lat"], "lng": lm["lng"]},
            }
        )

    messages.sort(key=lambda m: m["t"])
    for i, m in enumerate(messages):
        m["id"] = f"chn15-{i:05d}"

    bases = pick_bases(landmarks, flood, 8)
    fleet = (
        [("NDRF", "boat", 8, "B")] * 10
        + [("Fishermen", "boat", 6, "F")] * 8
        + [("Fire & Rescue", "truck", 12, "T")] * 5
        + [("TN Health", "medical", 4, "M")] * 3
        + [("IAF", "helicopter", 4, "H")] * 2
    )
    counters: dict[str, int] = {}
    teams = []
    for k, (org, asset, cap, prefix) in enumerate(fleet):
        counters[prefix] = counters.get(prefix, 0) + 1
        base = bases[k % len(bases)]
        lat, lng = jitter(base["lat"], base["lng"], 150)
        teams.append(
            {
                "call_sign": f"{prefix}-{counters[prefix]:02d}",
                "asset_type": asset,
                "capacity": cap,
                "organization": org,
                "base_name": base["name"],
                "lat": round(lat, 6),
                "lng": round(lng, 6),
            }
        )

    end = START + timedelta(hours=HOURS)
    meta = {
        "slug": "chennai-2015",
        "name": "Chennai floods, December 2015",
        "description": (
            "48 hours of synthetic SOS traffic modelled on the December 2015 Chennai floods: "
            f"{len(households)} households in real localities along the Adyar, the southern marshes and "
            "the Buckingham Canal, reported by relatives in English, Tamil, Hindi, Malayalam and Telugu, "
            "with duplicates, vague and stale reports. No real person's data."
        ),
        "source_url": "https://en.wikipedia.org/wiki/2015_South_Indian_floods",
        "starts_at": START.isoformat(),
        "ends_at": end.isoformat(),
        "message_count": len(messages),
        "household_count": len(households),
        "area": {
            "type": "MultiPolygon",
            "coordinates": [[[[79.98, 12.82], [80.33, 12.82], [80.33, 13.22], [79.98, 13.22], [79.98, 12.82]]]],
        },
        "center": [13.0, 80.2],
        "teams": teams,
        "households": [
            {k: v for k, v in h.items() if k not in ("locality", "landmark", "street", "depth", "onset", "danger_min")}
            | {"locality": h["locality"]["name"]}
            for h in households
        ],
    }
    with (OUT_DIR / "messages.jsonl").open("w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    (OUT_DIR / "dataset.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds: dict[str, int] = {}
    for m in messages:
        kinds[m["truth"]["kind"]] = kinds.get(m["truth"]["kind"], 0) + 1
    print(
        f"{len(messages)} messages {kinds}, {len(households)} households, {len(teams)} teams, bases: "
        + ", ".join(b["name"] for b in bases)
    )


if __name__ == "__main__":
    main()
