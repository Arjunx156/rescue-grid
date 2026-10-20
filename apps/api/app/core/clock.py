"""Time per disaster. Live events use the wall clock; replays run on a simulated clock.

Every service takes `now` as an argument, so scoring, ETAs and "waiting 40 min"
mean the same thing in a 60x replay as in a real flood.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.typing import EncodableT, FieldT

from app.core.redis import redis


def utcnow() -> datetime:
    return datetime.now(UTC)


def replay_key(disaster_id: uuid.UUID | str) -> str:
    return f"replay:{disaster_id}"


@dataclass(frozen=True)
class ReplayClock:
    status: str  # playing | paused | finished | idle
    speed: float
    sim_anchor: datetime
    wall_anchor: float

    def now(self, wall: float | None = None) -> datetime:
        if self.status != "playing":
            return self.sim_anchor
        elapsed = (wall if wall is not None else time.time()) - self.wall_anchor
        return self.sim_anchor + timedelta(seconds=elapsed * self.speed)

    def to_redis(self) -> dict[FieldT, EncodableT]:
        return {
            "status": self.status,
            "speed": str(self.speed),
            "sim_anchor": self.sim_anchor.isoformat(),
            "wall_anchor": str(self.wall_anchor),
        }

    @classmethod
    def from_redis(cls, data: Mapping[Any, Any]) -> ReplayClock | None:
        if not data:
            return None
        return cls(
            status=data["status"],
            speed=float(data["speed"]),
            sim_anchor=datetime.fromisoformat(data["sim_anchor"]),
            wall_anchor=float(data["wall_anchor"]),
        )


async def load_replay_clock(disaster_id: uuid.UUID | str) -> ReplayClock | None:
    return ReplayClock.from_redis(await redis().hgetall(replay_key(disaster_id)))


async def save_replay_clock(disaster_id: uuid.UUID | str, clock: ReplayClock) -> None:
    await redis().hset(replay_key(disaster_id), mapping=clock.to_redis())


async def disaster_now(disaster_id: uuid.UUID | str, status: str) -> datetime:
    if status != "replay":
        return utcnow()
    clock = await load_replay_clock(disaster_id)
    return clock.now() if clock else utcnow()
