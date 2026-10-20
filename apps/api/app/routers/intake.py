"""Bulk and operator intake: volunteer spreadsheets and helpline calls."""

from __future__ import annotations

import csv
import hashlib
import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.actions import intake
from app.core.clock import disaster_now
from app.core.deps import Coordinator, Session, disaster_or_404
from app.schemas.api import ManualIntakeIn

router = APIRouter(prefix="/api/v1/intake", tags=["intake"])
MAX_ROWS = 5000
MAX_BYTES = 5_000_000
TEXT_COLS = ("text", "message", "sos", "details", "request", "description")
PHONE_COLS = ("phone", "mobile", "contact", "phone_number", "contact_number")
NAME_COLS = ("name", "contact_name", "person")
TIME_COLS = ("time", "timestamp", "received_at", "date")
ID_COLS = ("id", "external_id", "row_id")
ADDRESS_COLS = ("address", "location", "area", "landmark", "locality")


class ImportResult(BaseModel):
    rows: int
    created: int
    duplicates: int
    errors: list[str]


def _pick(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    for n in names:
        if (v := row.get(n)) and v.strip():
            return v.strip()
    return None


def _when(raw: str | None, default: datetime) -> datetime:
    if not raw:
        return default
    for fmt in (None, "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%d/%m/%Y %I:%M %p", "%Y-%m-%d %H:%M:%S"):
        try:
            t = datetime.fromisoformat(raw) if fmt is None else datetime.strptime(raw, fmt)
            return t if t.tzinfo else t.replace(tzinfo=UTC)
        except ValueError:
            continue
    return default


@router.post("/import", response_model=ImportResult)
async def import_csv(
    claims: Coordinator, session: Session, disaster_id: uuid.UUID = Form(...), file: UploadFile = File(...)
) -> ImportResult:
    d = await disaster_or_404(session, claims, disaster_id)
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Keep imports under 5 MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The file has no header row")
    reader.fieldnames = [f.strip().lower().replace(" ", "_") for f in reader.fieldnames]
    if not set(reader.fieldnames) & set(TEXT_COLS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, f"Need a message column (one of: {', '.join(TEXT_COLS)})"
        )
    now = await disaster_now(d.id, d.status)
    created, dupes, errors, ids = 0, 0, [], []
    rows = 0
    for i, row in enumerate(reader, start=2):
        if rows >= MAX_ROWS:
            errors.append(f"Stopped at {MAX_ROWS} rows")
            break
        rows += 1
        body = _pick(row, TEXT_COLS)
        if not body:
            errors.append(f"Row {i}: empty message")
            continue
        if addr := _pick(row, ADDRESS_COLS):
            body = f"{body}. {addr}" if addr.lower() not in body.lower() else body
        lat = lng = None
        try:
            if row.get("lat") and row.get("lng"):
                lat, lng = float(row["lat"]), float(row["lng"])
        except ValueError:
            errors.append(f"Row {i}: lat/lng not numbers, ignored")
        ext = (
            _pick(row, ID_COLS)
            or hashlib.sha256(f"{body}|{_pick(row, PHONE_COLS)}|{_pick(row, TIME_COLS)}".encode()).hexdigest()[:32]
        )
        msg, is_new = await intake.ingest(
            session,
            intake.Incoming(
                disaster_id=d.id,
                channel="csv_import",
                text=body[:4000],
                received_at=_when(_pick(row, TIME_COLS), now),
                external_id=f"{d.id}:{ext}",
                sender_phone=_pick(row, PHONE_COLS),
                sender_name=_pick(row, NAME_COLS),
                pin=(lat, lng) if lat is not None and lng is not None else None,
                meta={"file": file.filename, "row": i, "imported_by": str(claims.user_id)},
            ),
        )
        if is_new:
            created += 1
            ids.append(msg.id)
        else:
            dupes += 1
    await intake.enqueue(ids)
    return ImportResult(rows=rows, created=created, duplicates=dupes, errors=errors[:50])


class ManualCreated(BaseModel):
    tracking_code: str
    message_id: uuid.UUID


@router.post("/manual", response_model=ManualCreated, status_code=201)
async def manual(body: ManualIntakeIn, disaster_id: uuid.UUID, claims: Coordinator, session: Session) -> ManualCreated:
    d = await disaster_or_404(session, claims, disaster_id)
    msg, _ = await intake.ingest(
        session,
        intake.Incoming(
            disaster_id=d.id,
            channel="helpline",
            text=body.text,
            received_at=await disaster_now(d.id, d.status),
            sender_phone=body.phone,
            sender_name=body.name,
            pin=(body.lat, body.lng) if body.lat is not None and body.lng is not None else None,
            meta={"operator": str(claims.user_id)},
        ),
    )
    await intake.enqueue([msg.id])
    return ManualCreated(tracking_code=msg.tracking_code, message_id=msg.id)
