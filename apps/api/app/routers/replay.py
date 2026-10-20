from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from app.actions import replay
from app.actions.serialize import disaster_out
from app.core.deps import Coordinator, Principal, Session, disaster_or_404
from app.schemas.api import DisasterOut, ReplaySpeedIn, ReplayStartIn
from app.sim.benchmark import output_path

router = APIRouter(prefix="/api/v1/replay", tags=["replay"])


@router.get("/datasets")
async def datasets() -> list[dict[str, Any]]:
    return replay.available()


class Started(BaseModel):
    disaster: DisasterOut
    state: dict[str, Any]


@router.post("/start", response_model=Started)
async def start(body: ReplayStartIn, claims: Coordinator, session: Session) -> Started:
    try:
        d = await replay.start(session, body.dataset, body.speed, body.autopilot)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No dataset {body.dataset!r}") from e
    s = await replay.state(d)
    return Started(disaster=disaster_out(d, d.started_at), state=s)


async def _replay(session: Session, claims: Principal, disaster_id: uuid.UUID):  # type: ignore[no-untyped-def]
    d = await disaster_or_404(session, claims, disaster_id)
    if d.status != "replay":
        raise HTTPException(status.HTTP_409_CONFLICT, "This disaster is not a replay")
    return d


@router.get("/{disaster_id}/state")
async def get_state(disaster_id: uuid.UUID, claims: Principal, session: Session) -> dict[str, Any]:
    return await replay.state(await _replay(session, claims, disaster_id))


@router.post("/{disaster_id}/{action}")
async def control(
    disaster_id: uuid.UUID, action: Literal["pause", "resume", "stop"], claims: Coordinator, session: Session
) -> dict[str, Any]:
    d = await _replay(session, claims, disaster_id)
    try:
        return await replay.control(session, d, action)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


@router.post("/{disaster_id}/speed/set")
async def set_speed(
    disaster_id: uuid.UUID, body: ReplaySpeedIn, claims: Coordinator, session: Session
) -> dict[str, Any]:
    d = await _replay(session, claims, disaster_id)
    return await replay.control(session, d, "speed", body.speed)


@router.delete("/{disaster_id}", status_code=204)
async def delete(disaster_id: uuid.UUID, claims: Coordinator, session: Session) -> Response:
    d = await _replay(session, claims, disaster_id)
    await replay.wipe(session, d)
    return Response(status_code=204)


@router.get("/benchmark")
async def benchmark(dataset: Annotated[str, Query(pattern=r"^[a-z0-9-]{1,64}$")] = "chennai-2015") -> Response:
    """The precomputed Rescue Grid vs first-come-first-served comparison (synthetic data only)."""
    path = output_path(dataset)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No benchmark yet. Run just bench.")
    return Response(path.read_bytes(), media_type="application/json", headers={"Cache-Control": "public, max-age=300"})
