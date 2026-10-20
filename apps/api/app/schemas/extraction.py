from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

WaterLevel = Literal[
    "none",
    "ankle",
    "knee",
    "waist",
    "chest",
    "neck",
    "first_floor",
    "second_floor",
    "roof",
    "unknown",
]
Need = Literal["rescue", "medical", "evacuation", "food", "water", "boat", "power", "information"]
StatusUpdate = Literal["none", "rescued", "safe", "false_alarm"]
Language = Literal["en", "ta", "hi", "ml", "te", "mixed"]

# rough severity order, used by triage and when merging reports
WATER_RANK: dict[str, int] = {
    "unknown": 0,
    "none": 0,
    "ankle": 1,
    "knee": 2,
    "waist": 3,
    "first_floor": 4,
    "chest": 4,
    "second_floor": 5,
    "neck": 6,
    "roof": 6,
}


class Vulnerable(BaseModel):
    elderly: int = Field(default=0, ge=0, le=100)
    child: int = Field(default=0, ge=0, le=100)
    infant: int = Field(default=0, ge=0, le=100)
    pregnant: int = Field(default=0, ge=0, le=20)
    disabled: int = Field(default=0, ge=0, le=100)
    medical: list[str] = Field(default_factory=list, description="conditions, e.g. dialysis")

    @field_validator("medical")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return sorted({m.strip().lower() for m in v if m.strip()})

    def total(self) -> int:
        return self.elderly + self.child + self.infant + self.pregnant + self.disabled


class Evidence(BaseModel):
    """The words in the message that back one claim."""

    field: str = Field(description="what this supports: people_count, water_level, elderly, medical:dialysis, ...")
    quote: str = Field(description="the exact words from the message")


class SosExtraction(BaseModel):
    """What the understanding step pulls out of one SOS message."""

    people_count: int | None = Field(default=None, ge=1, le=500, description="people needing help")
    vulnerable: Vulnerable = Field(default_factory=lambda: Vulnerable())
    location_text: str | None = Field(default=None, description="the most specific place description")
    locality: str | None = Field(default=None, description="neighbourhood, e.g. Velachery")
    landmarks: list[str] = Field(default_factory=list, description="named places mentioned")
    address: str | None = Field(default=None, description="door number, street, building")
    water_level: WaterLevel = "unknown"
    water_rising: bool | None = None
    needs: list[Need] = Field(default_factory=list)
    language: Language = "en"
    contact_name: str | None = None
    status_update: StatusUpdate = "none"
    summary: str = Field(default="", description="one line in English for a coordinator")
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list, description="a quote for every person, condition, level")

    @field_validator("needs")
    @classmethod
    def _unique_needs(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class Understanding(BaseModel):
    """Extraction plus what only local code may see (phones never leave the machine)."""

    extraction: SosExtraction
    phones: list[str] = Field(default_factory=list)
    provider: str
    model: str
    latency_ms: int = 0
    fallback_reason: str | None = None
    dropped_claims: list[str] = Field(default_factory=list)  # model claims with no quote behind them
    flags: list[str] = Field(default_factory=list)  # words in the message that try to instruct the system
