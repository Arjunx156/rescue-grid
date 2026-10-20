"""Multilingual keyword tables for reading flood SOS messages without a model.

Latin terms (English, Tanglish, Hinglish, Manglish) match on word boundaries.
Indic-script terms match as substrings, because Python's \\b breaks inside
Tamil, Devanagari, Malayalam and Telugu words at every vowel sign.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Terms:
    latin: tuple[str, ...] = ()
    indic: tuple[str, ...] = ()

    def pattern(self) -> re.Pattern[str]:
        parts = []
        if self.latin:
            parts.append(r"\b(?:" + "|".join(self.latin) + r")\b")
        if self.indic:
            # drop a final virama so "കൈക്കുഞ്ഞ്" also finds "കൈക്കുഞ്ഞുണ്ട്" (has an infant)
            stems = (t.rstrip("്்్्") for t in self.indic)
            parts.append("(?:" + "|".join(re.escape(t) for t in stems) + ")")
        return re.compile("|".join(parts) or r"(?!x)x", re.IGNORECASE)


# --- numbers -----------------------------------------------------------------

NUMBER_WORDS: dict[str, int] = {
    # english
    "one": 1,
    "a": 1,
    "an": 1,
    "single": 1,
    "two": 2,
    "both": 2,
    "couple": 2,
    "pair": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "dozen": 12,
    "fifteen": 15,
    "twenty": 20,
    # tanglish / manglish / telugu romanised
    "onnu": 1,
    "oru": 1,
    "rendu": 2,
    "randu": 2,
    "irandu": 2,
    "moonu": 3,
    "munu": 3,
    "moonnu": 3,
    "moodu": 3,
    "naalu": 4,
    "nalu": 4,
    "naalugu": 4,
    "anju": 5,
    "anchu": 5,
    "aidu": 5,
    "aaru": 6,
    "ezhu": 7,
    "yezhu": 7,
    "edu": 7,
    "ettu": 8,
    "enimidi": 8,
    "ombodhu": 9,
    "onpathu": 9,
    "tommidi": 9,
    "pathu": 10,
    "padi": 10,
    # hinglish
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "chhe": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
    # tamil
    "ஒரு": 1,
    "ஒன்று": 1,
    "இரண்டு": 2,
    "ரெண்டு": 2,
    "மூன்று": 3,
    "மூணு": 3,
    "நான்கு": 4,
    "நாலு": 4,
    "ஐந்து": 5,
    "அஞ்சு": 5,
    "ஆறு": 6,
    "ஏழு": 7,
    "எட்டு": 8,
    "ஒன்பது": 9,
    "பத்து": 10,
    # hindi
    "एक": 1,
    "दो": 2,
    "तीन": 3,
    "चार": 4,
    "पांच": 5,
    "पाँच": 5,
    "छह": 6,
    "छः": 6,
    "सात": 7,
    "आठ": 8,
    "नौ": 9,
    "दस": 10,
    # malayalam
    "ഒന്ന്": 1,
    "ഒരു": 1,
    "രണ്ട്": 2,
    "മൂന്ന്": 3,
    "നാല്": 4,
    "അഞ്ച്": 5,
    "ആറ്": 6,
    "ഏഴ്": 7,
    "എട്ട്": 8,
    "ഒമ്പത്": 9,
    "പത്ത്": 10,
    # telugu
    "ఒకటి": 1,
    "ఒక": 1,
    "రెండు": 2,
    "ఇద్దరు": 2,
    "మూడు": 3,
    "ముగ్గురు": 3,
    "నాలుగు": 4,
    "నలుగురు": 4,
    "ఐదు": 5,
    "ఐదుగురు": 5,
    "ఆరు": 6,
    "ఏడు": 7,
    "ఎనిమిది": 8,
    "తొమ్మిది": 9,
    "పది": 10,
}
# words that are numbers only in a counting context ("a", "do", "das" are everyday words)
WEAK_NUMBERS = {"a", "an", "do", "das", "edu", "padi", "aaru", "ஆறு", "single", "pair"}

NUM = r"(\d{1,3}|[^\s\d,.;:!?()]+)"  # a digit run or one word that may be a number

# --- people ------------------------------------------------------------------

PEOPLE_UNITS = Terms(
    latin=(
        r"people",
        r"peoples",
        r"persons?",
        r"ppl",
        r"members?",
        r"family members",
        r"of us",
        r"souls",
        r"individuals",
        r"adults?",
        r"peru",
        r"per",
        r"paer",
        r"pear",
        r"log",
        r"logon",
        r"mandi",
        r"perum",
    ),
    indic=("பேர்", "நபர்", "लोग", "व्यक्ति", "सदस्य", "जन", "പേർ", "ആളുകൾ", "మంది", "వ్యక్తులు"),
)
FAMILY_OF = re.compile(r"\b(?:family|families|household) of (\d{1,3}|\w+)", re.IGNORECASE)
WE_ARE = re.compile(r"\b(?:we are|we're|there are|totally|total|around|about)\s+(\d{1,3}|\w+)\b", re.I)
# collective numerals that mean "N people" on their own
COLLECTIVE = {
    "இருவர்": 2,
    "மூவர்": 3,
    "நால்வர்": 4,
    "ఇద్దరు": 2,
    "ముగ్గురు": 3,
    "నలుగురు": 4,
    "ఐదుగురు": 5,
    "ఆరుగురు": 6,
    "ഇരുവരും": 2,
    "മൂവരും": 3,
}

KIN_SINGLE = Terms(
    latin=(
        r"mother",
        r"father",
        r"mom",
        r"mum",
        r"dad",
        r"wife",
        r"husband",
        r"son",
        r"daughter",
        r"brother",
        r"sister",
        r"uncle",
        r"aunt",
        r"aunty",
        r"grandmother",
        r"grandfather",
        r"grandma",
        r"grandpa",
        r"amma",
        r"appa",
        r"paati",
        r"patti",
        r"thatha",
        r"thaatha",
        r"ammachi",
        r"appachan",
        r"ammamma",
        r"nanamma",
        r"thata",
        r"maa",
        r"papa",
        r"bhai",
        r"behen",
        r"dadi",
        r"dada",
        r"nani",
        r"nana",
        r"thambi",
        r"akka",
        r"thangachi",
        r"manaivi",
        r"purushan",
        r"paiyan",
        r"ponnu",
        r"neighbou?r",
    ),
    indic=(
        "அம்மா",
        "அப்பா",
        "பாட்டி",
        "தாத்தா",
        "மனைவி",
        "கணவர்",
        "மகன்",
        "மகள்",
        "அண்ணன்",
        "தம்பி",
        "அக்கா",
        "தங்கை",
        "माँ",
        "मां",
        "पिता",
        "पापा",
        "पत्नी",
        "पति",
        "बेटा",
        "बेटी",
        "दादी",
        "दादा",
        "नानी",
        "नाना",
        "അമ്മ",
        "അച്ഛൻ",
        "ഭാര്യ",
        "ഭർത്താവ്",
        "മകൻ",
        "മകൾ",
        "അമ്മൂമ്മ",
        "അപ്പൂപ്പൻ",
        "అమ్మ",
        "నాన్న",
        "భార్య",
        "భర్త",
        "కొడుకు",
        "కూతురు",
        "అమ్మమ్మ",
        "తాతయ్య",
    ),
)
KIN_PAIR = Terms(
    latin=(
        r"parents",
        r"grandparents",
        r"in-?laws",
        r"couple",
        r"amma appa",
        r"amma and appa",
        r"appa amma",
        r"mom and dad",
        r"mother and father",
        r"paati thatha",
    ),
    indic=("பெற்றோர்", "माता-पिता", "माता पिता", "മാതാപിതാക്കൾ", "తల్లిదండ్రులు"),
)
SELF = re.compile(r"\b(?:i am|i'm|im|me and|myself|i and)\b", re.IGNORECASE)

# --- vulnerability -----------------------------------------------------------

ELDERLY = Terms(
    latin=(
        r"elderly",
        r"old (?:man|woman|lady|men|women|people|couple|parents|age|person)",
        r"aged",
        r"senior citizens?",
        r"seniors?",
        r"grand ?mother",
        r"grand ?father",
        r"grandma",
        r"grandpa",
        r"grandparents",
        r"paati",
        r"patti",
        r"thatha",
        r"thaatha",
        r"vayasana(?:vanga|var)?",
        r"vayasaana",
        r"periyavanga",
        r"budhe",
        r"budhi",
        r"buzurg",
        r"dadi",
        r"dada ji",
        r"nani",
        r"ammachi",
        r"appachan",
        r"ammamma",
        r"nanamma",
    ),
    indic=(
        "வயதான",
        "வயசான",
        "முதியவர்",
        "முதியோர்",
        "பாட்டி",
        "தாத்தா",
        "बुजुर्ग",
        "बूढ़े",
        "बूढ़ी",
        "दादी",
        "दादा",
        "नानी",
        "वृद्ध",
        "പ്രായമായ",
        "വൃദ്ധ",
        "അമ്മൂമ്മ",
        "അപ്പൂപ്പൻ",
        "മുത്തശ്ശി",
        "വയോധിക",
        "వృద్ధ",
        "ముసలి",
        "అమ్మమ్మ",
        "నాయనమ్మ",
        "తాతయ్య",
    ),
)
ELDERLY_PLURAL = re.compile(
    r"\b(?:elderly (?:people|parents|couple)|old (?:people|couple|parents|men|women)|"
    r"grandparents|senior citizens|seniors|paati thatha|paati and thatha)\b",
    re.IGNORECASE,
)
AGE = re.compile(r"\b(\d{1,3})\s*(?:-|\s)?(?:years?|yrs?|yr|y/o|yo|vayasu|saal|vayassu)\b", re.I)
AGED = re.compile(r"\baged?\s+(\d{1,3})\b", re.IGNORECASE)
# "6 month old" is an infant; "8 months pregnant" is not
MONTHS_OLD = re.compile(r"\b(\d{1,2})\s*(?:-|\s)?(?:months?|mnths?|mths?)\s*-?\s*old\b", re.IGNORECASE)

CHILD = Terms(
    latin=(
        r"child",
        r"children",
        r"kids?",
        r"boy",
        r"girl",
        r"school ?going",
        r"kuzhandhai",
        r"kulandhai",
        r"kozhandha",
        r"kuzhandhaigal",
        r"pasanga",
        r"pillainga",
        r"bachche",
        r"bachcha",
        r"bacche",
        r"baccha",
        r"bachchi",
        r"kunju",
        r"kuttikal",
        r"pillalu",
        r"twins",
    ),
    indic=(
        "குழந்தை",
        "பிள்ளைகள்",
        "சிறுவர்",
        "சிறுமி",
        "बच्चा",
        "बच्चे",
        "बच्ची",
        "बच्चों",
        "കുട്ടി",
        "കുഞ്ഞ്",
        "കുഞ്ഞുങ്ങൾ",
        "పిల్లలు",
        "పిల్లవాడు",
        "చిన్నారి",
        "పాప",
    ),
)
CHILD_PLURAL = re.compile(
    r"\b(?:children|kids|twins|pasanga|pillainga|bachche|bacche|kuttikal|pillalu|kuzhandhaigal)\b|"
    r"குழந்தைகள்|பிள்ளைகள்|बच्चे|बच्चों|കുട്ടികൾ|കുഞ്ഞുങ്ങൾ|పిల్లలు",
    re.IGNORECASE,
)
INFANT = Terms(
    latin=(
        r"infants?",
        r"new ?born",
        r"babies",
        r"baby",
        r"toddler",
        r"(?:\d{1,2}|few) ?months? old",
        r"kai kuzhandhai",
        r"kaikuzhandhai",
        r"pacha kuzhandhai",
        r"chhota bachcha",
        r"shishu",
    ),
    indic=("கைக்குழந்தை", "பச்சிளம்", "பிறந்த குழந்தை", "शिशु", "नवजात", "दूधमुंहा", "കൈക്കുഞ്ഞ്", "നവജാത", "శిశువు", "పసిపాప", "పసికందు"),
)
PREGNANT = Terms(
    latin=(
        r"pregnant",
        r"pregnancy",
        r"expecting",
        r"garbini",
        r"karpini",
        r"garbhini",
        r"garbhvati",
        r"due date",
        r"\d+ ?months? pregnant",
        r"full term",
    ),
    indic=("கர்ப்பிணி", "கர்ப்பமாக", "गर्भवती", "प्रेग्नेंट", "ഗർഭിണി", "గర్భిణి", "గర్భవతి"),
)
DISABLED = Terms(
    latin=(
        r"disabled",
        r"disability",
        r"wheel ?chair",
        r"handicapped",
        r"paraly[sz]ed",
        r"paralysis",
        r"bed ?ridden",
        r"cannot walk",
        r"can'?t walk",
        r"unable to walk",
        r"differently abled",
        r"blind",
        r"deaf",
        r"amputee",
        r"special needs",
        r"autistic",
        r"walk panna mudiyadhu",
        r"nadakka mudiyadhu",
        r"viklang",
        r"divyang",
    ),
    indic=(
        "மாற்றுத்திறனாளி",
        "ஊனமுற்ற",
        "படுத்த படுக்கை",
        "நடக்க முடியாத",
        "विकलांग",
        "दिव्यांग",
        "अपाहिज",
        "चल नहीं",
        "बिस्तर पर",
        "ഭിന്നശേഷി",
        "വികലാംഗ",
        "കിടപ്പിലായ",
        "നടക്കാൻ കഴിയാത്ത",
        "వికలాంగ",
        "దివ్యాంగ",
        "మంచాన",
        "నడవలేని",
    ),
)

# condition -> how it reads to a medic; first match per condition wins
MEDICAL: dict[str, Terms] = {
    "dialysis": Terms((r"dialysis", r"kidney (?:patient|failure)"), ("டயாலிசிஸ்", "डायलिसिस", "ഡയാലിസിസ്", "డయాలసిస్")),
    "oxygen": Terms(
        (
            r"oxygen",
            r"ventilator",
            r"o2 (?:cylinder|support)",
            r"breathing (?:problem|difficulty|issue)",
            r"can'?t breathe",
            r"breathless",
        ),
        ("ஆக்ஸிஜன்", "மூச்சுத் திணறல்", "ऑक्सीजन", "सांस", "ഓക്സിജൻ", "ശ്വാസം", "ఆక్సిజన్", "శ్వాస"),
    ),
    "labour": Terms(
        (r"labou?r pain", r"in labou?r", r"delivery pain", r"water broke", r"contractions", r"prasava vali"),
        ("பிரசவ வலி", "प्रसव पीड़ा", "प्रसव", "പ്രസവ വേദന", "ప్రసవ నొప్పి"),
    ),
    "cardiac": Terms(
        (r"heart (?:patient|attack|problem|condition|surgery)", r"cardiac", r"chest pain", r"bypass", r"pacemaker"),
        ("இதய", "மாரடைப்பு", "दिल", "हार्ट", "ഹൃദയ", "గుండె"),
    ),
    "diabetes": Terms(
        (r"insulin", r"diabetic", r"diabetes", r"sugar patient", r"sugar level"),
        ("இன்சுலின்", "சர்க்கரை நோய்", "इंसुलिन", "शुगर", "ഇൻസുലിൻ", "പ്രമേഹ", "ఇన్సులిన్", "షుగర్"),
    ),
    "unconscious": Terms(
        (r"unconscious", r"fainted", r"not responding", r"collapsed", r"fits", r"seizures?", r"stroke"),
        ("மயக்கம்", "बेहोश", "ബോധം", "സ്പൃഹ", "స్పృహ"),
    ),
    "injury": Terms(
        (
            r"injured",
            r"injury",
            r"bleeding",
            r"fracture",
            r"broken (?:leg|arm|bone)",
            r"wound",
            r"electrocuted",
            r"current shock",
            r"snake ?bite",
        ),
        ("காயம்", "ரத்தம்", "घायल", "खून", "പരിക്ക്", "గాయం", "రక్తం"),
    ),
    "cancer": Terms((r"cancer", r"chemo(?:therapy)?", r"tumou?r"), ("புற்றுநோய்", "कैंसर", "കാൻസർ", "క్యాన్సర్")),
    "fever": Terms(
        (r"high fever", r"fever", r"vomiting", r"diarrh(?:o)?ea", r"jaram", r"kaichal", r"bukhar"),
        ("காய்ச்சல்", "बुखार", "പനി", "జ్వరం"),
    ),
    "post_surgery": Terms(
        (r"post[- ]?op(?:erative)?", r"just operated", r"(?:had|after|recent|post) ?(?:a )?surgery"),
        ("அறுவை", "ऑपरेशन", "ശസ്ത്രക്രിയ", "ఆపరేషన్"),
    ),
    "medication": Terms(
        (r"medicines?", r"tablets", r"bp patient", r"blood pressure", r"asthma", r"patient", r"sick", r"ill"),
        ("மருந்து", "நோயாளி", "दवा", "दवाई", "मरीज", "बीमार", "മരുന്ന്", "രോഗി", "మందులు", "రోగి"),
    ),
}
CRITICAL_MEDICAL = {"dialysis", "oxygen", "labour", "cardiac", "unconscious", "injury"}

# --- water -------------------------------------------------------------------

WATER: dict[str, Terms] = {
    "roof": Terms(
        (
            r"roof ?top",
            r"roof",
            r"terrace",
            r"on top of (?:the )?(?:house|building)",
            r"mottai maadi",
            r"motta maadi",
            r"chhat",
            r"chat par",
            r"dabaa?",
            r"terrace mele",
            r"submerged completely",
            r"fully submerged",
        ),
        ("மொட்டை மாடி", "छत पर", "छत", "ടെറസ്", "മേൽക്കൂര", "డాబా", "మేడ మీద"),
    ),
    "neck": Terms(
        (
            r"neck deep",
            r"neck level",
            r"up ?to (?:the |our )?neck",
            r"(?:till|upto) neck",
            r"neck high",
            r"kazhuthu (?:varai|varaikum|alavu)",
            r"gale tak",
            r"gardan tak",
            r"head level",
            r"above head",
            r"over head",
            r"drowning",
        ),
        ("கழுத்து வரை", "கழுத்தளவு", "गले तक", "गर्दन तक", "കഴുത്തോളം", "കഴുത്ത് വരെ", "మెడ వరకు"),
    ),
    "second_floor": Terms(
        (r"second floor", r"2nd floor", r"third floor", r"3rd floor", r"irandaam maadi"),
        ("இரண்டாவது மாடி", "दूसरी मंजिल", "രണ്ടാം നില", "రెండవ అంతస్తు"),
    ),
    "chest": Terms(
        (
            r"chest (?:deep|level|high)",
            r"up ?to (?:the |our )?chest",
            r"(?:till|upto) chest",
            r"nenju (?:varai|alavu)",
            r"seene tak",
            r"chhati tak",
            r"shoulder (?:deep|level|high)",
            r"up ?to (?:the |our )?shoulders?",
        ),
        ("மார்பு வரை", "நெஞ்சு வரை", "सीने तक", "छाती तक", "നെഞ്ചോളം", "ఛాతీ వరకు"),
    ),
    "first_floor": Terms(
        (
            r"first floor",
            r"1st floor",
            r"upstairs",
            r"ground floor (?:is )?(?:fully |completely )?(?:submerged|under water|flooded|drowned)",
            r"maadi(?:yil|la)?",
            r"upper floor",
            r"pehli manzil",
            r"mel maadi",
        ),
        ("முதல் மாடி", "மாடியில்", "मंजिल", "ഒന്നാം നില", "మొదటి అంతస్తు"),
    ),
    "waist": Terms(
        (
            r"waist (?:deep|level|high)",
            r"up ?to (?:the |our )?waist",
            r"(?:till|upto) waist",
            r"waist",
            r"hip",
            r"idupu (?:varai|alavu)",
            r"kamar tak",
        ),
        ("இடுப்பு வரை", "कमर तक", "അരയോളം", "നടുവോളം", "నడుము వరకు"),
    ),
    "knee": Terms(
        (
            r"knee (?:deep|level|high)",
            r"up ?to (?:the |our )?knees?",
            r"(?:till|upto) knees?",
            r"knee-deep",
            r"mutti (?:varai|alavu)",
            r"ghutno tak",
            r"ghutne tak",
            r"water (?:entered|entering|inside|is inside) (?:the |our |my )?(?:house|home)",
            r"inside (?:the |our )?house",
            r"ghutne",
        ),
        (
            "முழங்கால்",
            "முட்டி வரை",
            "வீட்டுக்குள் தண்ணீர்",
            "घुटनों तक",
            "घुटने",
            "घर में पानी",
            "മുട്ടോളം",
            "വീടിനുള്ളിൽ വെള്ളം",
            "మోకాళ్ళ",
            "మోకాలి",
            "ఇంట్లోకి నీరు",
        ),
    ),
    "ankle": Terms(
        (r"ankle", r"street (?:is )?flooded", r"road (?:is )?flooded", r"water logging", r"waterlogged"),
        ("கணுக்கால்", "टखने", "കണങ്കാൽ", "చీలమండ"),
    ),
}
FEET = re.compile(r"(\d+(?:\.\d+)?)\s*(?:ft|feet|foot|adi|feets)\b|(\d+(?:\.\d+)?)\s*அடி", re.IGNORECASE)
METRES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:m|mtr|metres?|meters?)\b(?! ?(?:away|from|distance))", re.I)
RISING = Terms(
    latin=(
        r"rising",
        r"increasing",
        r"going up",
        r"keeps? (?:on )?(?:rising|increasing|coming)",
        r"level (?:is )?up",
        r"more water",
        r"rising fast",
        r"y?eri ?k?kitt?(?:e|u)",
        r"y?eri ?kittu",
        r"adhigam(?:a)?(?:agudhu|aagudhu)",
        r"badh raha",
        r"badhta",
        r"kooduthu",
        r"perugutondi",
    ),
    indic=(
        "ஏறிக்கொண்டே",
        "ஏறுகிறது",
        "அதிகரித்து",
        "உயர்ந்து",
        "बढ़ रहा",
        "बढ़ रही",
        "बढ़ता",
        "ഉയരുന്നു",
        "കൂടുന്നു",
        "పెరుగుతోంది",
        "పెరుగుతున్నా",
    ),
)

# --- needs -------------------------------------------------------------------

NEEDS: dict[str, Terms] = {
    "rescue": Terms(
        (
            r"rescue",
            r"stuck",
            r"stranded",
            r"trapped",
            r"marooned",
            r"save us",
            r"save them",
            r"save my",
            r"kaapa?th(?:u|a)nga",
            r"kapathunga",
            r"kaapaathunga",
            r"sikki",
            r"maatikitt?(?:u|om)",
            r"bachao",
            r"bachaiye",
            r"fanse",
            r"phanse",
            r"madad",
            r"rakshikk?(?:ane|uka)",
            r"kudungi",
            r"kapadandi",
            r"chikkukunn?aru",
            r"udhavi",
        ),
        (
            "காப்பாற்று",
            "உதவி",
            "சிக்கி",
            "மீட்க",
            "बचाओ",
            "बचाइए",
            "मदद",
            "फंसे",
            "രക്ഷിക്ക",
            "സഹായ",
            "കുടുങ്ങി",
            "కాపాడండి",
            "సహాయం",
            "చిక్కుకు",
        ),
    ),
    "evacuation": Terms(
        (
            r"evacuat\w*",
            r"shift(?:ing)? (?:us|them)",
            r"take (?:us|them) out",
            r"relief camp",
            r"move (?:us|them)",
            r"get (?:us|them) out",
        ),
        ("வெளியேற்ற", "निकाल", "ഒഴിപ്പിക്ക", "తరలించ"),
    ),
    "medical": Terms(
        (r"doctor", r"ambulance", r"medical", r"hospital", r"medicines?", r"first aid"),
        ("மருத்துவ", "டாக்டர்", "डॉक्टर", "एम्बुलेंस", "ഡോക്ടർ", "ആംബുലൻസ്", "డాక్టర్", "అంబులెన్స్"),
    ),
    "food": Terms(
        (
            r"food",
            r"hungry",
            r"starving",
            r"milk",
            r"no food",
            r"saapadu",
            r"sapadu",
            r"khana",
            r"bhojan",
            r"bhakshanam",
            r"annam",
            r"biscuits?",
            r"rations?",
        ),
        ("உணவு", "சாப்பாடு", "பால்", "खाना", "भोजन", "दूध", "ഭക്ഷണം", "പാൽ", "ఆహారం", "భోజనం", "పాలు"),
    ),
    "water": Terms(
        (
            r"drinking water",
            r"no water to drink",
            r"kudi ?neer",
            r"kudineer",
            r"peene ka paani",
            r"thirsty",
            r"water bottles?",
        ),
        ("குடிநீர்", "पीने का पानी", "കുടിവെള്ളം", "తాగునీరు"),
    ),
    "boat": Terms(
        (r"boats?", r"padagu", r"padaku", r"naav", r"vallam", r"padava"), ("படகு", "नाव", "വള്ളം", "ബോട്ട്", "పడవ")
    ),
    "power": Terms(
        (
            r"no (?:power|current|electricity)",
            r"power cut",
            r"current illa",
            r"phone (?:battery|charge)",
            r"battery (?:low|dying)",
            r"bijli nahi",
        ),
        ("மின்சாரம் இல்லை", "கரண்ட் இல்லை", "बिजली नहीं", "കറന്റ് ഇല്ല", "కరెంట్ లేదు"),
    ),
    "information": Terms(
        (
            r"any (?:news|update|information)",
            r"not reachable",
            r"no contact",
            r"unable to contact",
            r"can'?t reach",
            r"phone switched off",
            r"no response",
        ),
        ("தொடர்பு இல்லை", "संपर्क नहीं", "ബന്ധപ്പെടാൻ", "సంప్రదించ"),
    ),
}

# "no rescue needed" from a relief camp asking for food is not a rescue request
NO_RESCUE = re.compile(
    r"\b(?:no|not|don'?t|do not|doesn'?t|without)\b[^.,;]{0,15}\b(?:rescue|evacuation|boat)\b|"
    r"\b(?:rescue|evacuation|boat)\b[^.,;]{0,6}\bnot (?:needed|required|necessary)\b",
    re.IGNORECASE,
)

# --- status updates for stale reports ---------------------------------------

RESCUED = Terms(
    latin=(
        r"(?:have|has|were|was|got|been|are|is) (?:been )?rescued",
        r"rescued (?:safely|already|now)",
        r"already rescued",
        r"(?:are|is) (?:now )?safe(?: now)?",
        r"reached (?:safely|safe|relief camp|camp)",
        r"already evacuated",
        r"(?:have|has) been evacuated",
        r"moved to (?:a )?(?:relief )?camp",
        r"no (?:more|longer) (?:help )?(?:needed|required)",
        r"please ignore",
        r"kindly ignore",
        r"pls ignore",
        r"thank(?:s| you) (?:all|everyone)[^.]*safe",
        r"kaapathitt?anga",
        r"safe(?:-a)? irukk?anga",
        r"bacha liya",
        r"surakshit",
    ),
    indic=(
        "மீட்கப்பட்ட",
        "காப்பாற்றப்பட்ட",
        "பாதுகாப்பாக உள்ள",
        "बचा लिया",
        "सुरक्षित हैं",
        "बचाए गए",
        "രക്ഷപ്പെടുത്തി",
        "സുരക്ഷിതരാണ്",
        "రక్షించారు",
        "సురక్షితంగా",
    ),
)
NOT_RESCUED = re.compile(
    r"\b(?:not|yet to be|still not|never|nobody has|no one has|none)\b[^.]{0,20}\b(?:rescued|safe|evacuated)\b|"
    r"\bunsafe\b|\bnot safe\b",
    re.IGNORECASE,
)
FALSE_ALARM = Terms(
    latin=(
        r"false (?:alarm|message|news|info)",
        r"fake (?:message|news|sos)",
        r"wrong (?:number|address|info)",
        r"prank",
        r"old message",
        r"outdated",
    ),
    indic=("பொய்யான", "झूठी", "വ്യാജ", "తప్పుడు"),
)

# --- language markers for romanised text ------------------------------------

ROMAN_MARKERS: dict[str, Terms] = {
    "ta": Terms(
        (
            r"kaapa?thunga",
            r"kapathunga",
            r"irukk?anga",
            r"irukkom",
            r"maatikitt?\w*",
            r"sikki\w*",
            r"romba",
            r"seekiram",
            r"sikiram",
            r"veettu?la",
            r"veedu",
            r"thanni",
            r"vellam",
            r"paati",
            r"thatha",
            r"kuzhandhai",
            r"pannunga",
            r"anupunga",
            r"illa",
            r"irukku",
            r"udhavi",
            r"peru",
            r"enga",
            r"naanga",
            r"avanga",
        )
    ),
    "hi": Terms(
        (
            r"bachao",
            r"madad",
            r"paani",
            r"ghar",
            r"fanse",
            r"phanse",
            r"jaldi",
            r"kripya",
            r"hamare",
            r"bachche",
            r"log hain",
            r"hai",
            r"hain",
            r"nahi",
            r"kuch",
            r"bhai",
            r"chhat",
        )
    ),
    "ml": Terms(
        (
            r"rakshikk\w*",
            r"sahayikk\w*",
            r"kudungi\w*",
            r"ammachi",
            r"appachan",
            r"kunju",
            r"veettil",
            r"vellam kayari",
            r"und",
            r"illa(?:nu)?",
            r"ente",
            r"njangal",
        )
    ),
    "te": Terms(
        (
            r"kapadandi",
            r"chikkukunn\w*",
            r"neellu",
            r"intlo",
            r"mandi",
            r"pillalu",
            r"ammamma",
            r"sahayam",
            r"vunnaru",
            r"unnaru",
            r"maa intlo",
        )
    ),
}

SCRIPTS: dict[str, tuple[int, int]] = {
    "ta": (0x0B80, 0x0BFF),
    "hi": (0x0900, 0x097F),
    "ml": (0x0D00, 0x0D7F),
    "te": (0x0C00, 0x0C7F),
}

# --- location cues -----------------------------------------------------------

# strong cues introduce a place whatever the casing; weak ones need a capital or digit
STRONG_CUES = re.compile(
    r"(?:near|behind|opposite|opp|next to|beside|close to|in front|adjacent|backside|back of|located|"
    r"address|pakkathula|ke paas|ke peeche|ke saamne|aduthu|daggara|venuka)",
    re.IGNORECASE,
)
LOCATION_CUES = re.compile(
    r"\b(?:near(?:by)?|behind|opposite|opp\.?|next to|beside|besides|close to|in front of|"
    r"adjacent to|backside of|back of|after|before|at|in|on|located at|address[:\s]|"
    r"pakkathula|ke paas|ke peeche|ke saamne|aduthu|daggara|venuka)\s+"
    r"([^,.;!?\n()]{3,80})",
    re.IGNORECASE,
)
ADDRESS = re.compile(
    r"\b(?:(?:door|house|flat|plot|old|new)\s*(?:no\.?|number|#)\s*[\w/-]+|no\.?\s*\d+[\w/-]*|#\s*\d+[\w/-]*|"
    r"\d+[a-z]?/\d+[a-z]?)"
    r"(?:[,\s]+[^,.;!?\n]{2,60}?(?:street|st|road|rd|salai|nagar|colony|avenue|lane|cross|layout|"
    r"apartments?|flats|towers|block|enclave|garden|gardens|residency|main road))?",
    re.IGNORECASE,
)
PLACE_SUFFIX = re.compile(
    r"\b([A-Z][\w.']*(?:\s+[A-Z0-9][\w.']*){0,4}\s+(?i:Street|St|Road|Rd|Salai|Nagar|Colony|Avenue|Lane|"
    r"Layout|Apartments?|Flats|Towers|Enclave|Gardens?|Residency|Puram|Pakkam|Pettai|Kuppam|Cross|Main Road|"
    r"Extension|Extn|Bridge|Temple|Church|Mosque|Masjid|School|College|Hospital|Depot|Bus Stand|Bus Stop|"
    r"Station|Lake|Kovil|Koil|Market|Signal|Junction))\b"
)
# words that end a place description ("Kotturpuram have been rescued" -> "Kotturpuram")
SPAN_STOP = re.compile(
    r"\s+(?:have|has|had|is|are|was|were|and|but|please|pls|plz|call|contact|water|with|who|which|"
    r"stuck|trapped|stranded|need|needs|since|from|for|they|we|our|my|it|urgent|help)\b.*$",
    re.IGNORECASE,
)
# Indic postpositions follow the place: "<place> அருகில்" = "near <place>"
INDIC_CUES = re.compile(
    r"((?:\S+\s+)?\S+)\s+(?:அருகில்|அருகே|பக்கத்தில்|பின்னால்|எதிரில்|எதிரே|கிட்ட|"
    r"के पास|के पीछे|के सामने|में|దగ్గర|వెనుక|ఎదురుగా|അടുത്ത്|സമീപം|പിന്നിൽ)"
)
ELDERLY_KIN = re.compile(
    r"\b(?:grand ?mother|grand ?father|grandma|grandpa|paati|patti|thatha|thaatha|dadi|dada|nani|nana|"
    r"ammachi|appachan|ammamma|nanamma)\b|பாட்டி|தாத்தா|दादी|दादा|नानी|नाना|അമ്മൂമ്മ|അപ്പൂപ്പൻ|అమ్మమ్మ|తాతయ్య",
    re.IGNORECASE,
)
NAME_PATTERNS = re.compile(
    r"\b(?i:name(?: is)?[:\s]+|contact(?: person)?[:\s]+|call|ask for|speak to|mr\.?|mrs\.?|ms\.?|shri|smt\.?)\s*"
    r"([A-Z][a-z]{2,}(?:\s[A-Z][a-z]{1,})?)"
)
PHONE = re.compile(
    r"(?<!\d)(?:\+?91[\s.-]?|0)?([5-9]\d{4}[\s.-]?\d{5})(?!\d)|(?<!\d)(0?44[\s.-]?\d{4}[\s.-]?\d{4})(?!\d)"
)
