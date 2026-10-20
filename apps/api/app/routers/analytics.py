from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.actions import stats
from app.core.deps import Session, Staff, disaster_or_404

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/summary")
async def summary(disaster_id: uuid.UUID, claims: Staff, session: Session) -> dict[str, Any]:
    d = await disaster_or_404(session, claims, disaster_id)
    return await stats.summary(session, d)


@router.get("/heatmap")
async def heatmap(disaster_id: uuid.UUID, claims: Staff, session: Session) -> list[list[float]]:
    await disaster_or_404(session, claims, disaster_id)
    return await stats.heatmap(session, disaster_id)


@router.get("/teams")
async def teams(disaster_id: uuid.UUID, claims: Staff, session: Session) -> list[dict[str, Any]]:
    await disaster_or_404(session, claims, disaster_id)
    return await stats.team_utilisation(session, disaster_id)
