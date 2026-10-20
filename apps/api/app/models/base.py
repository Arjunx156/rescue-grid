from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)
    # fetch server-set columns (created_at, updated_at) with RETURNING at flush, so reading them
    # after commit never triggers a lazy load outside the async context
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())


def Point() -> Geometry:  # noqa: N802 (reads like a type in column declarations)
    return Geometry("POINT", srid=4326, spatial_index=False)


def MultiPolygon() -> Geometry:  # noqa: N802
    return Geometry("MULTIPOLYGON", srid=4326, spatial_index=False)


def LineString() -> Geometry:  # noqa: N802
    return Geometry("LINESTRING", srid=4326, spatial_index=False)


def tstz() -> DateTime:
    return DateTime(timezone=True)
