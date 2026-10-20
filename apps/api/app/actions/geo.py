"""PostGIS <-> plain coordinates. Everything outside this module speaks (lat, lng)."""

from __future__ import annotations

from typing import Any

from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, mapping, shape

SRID = 4326


def point(lat: float, lng: float) -> WKTElement:
    return WKTElement(f"POINT({lng} {lat})", srid=SRID)


def line(coords: list[tuple[float, float]]) -> WKTElement | None:
    """coords as (lat, lng) pairs."""
    if len(coords) < 2:
        return None
    return WKTElement(LineString([(lng, lat) for lat, lng in coords]).wkt, srid=SRID)


def multipolygon(geojson: dict[str, Any]) -> WKTElement:
    g = shape(geojson)
    if isinstance(g, Polygon):
        g = MultiPolygon([g])
    if not isinstance(g, MultiPolygon):
        raise ValueError("area must be a Polygon or MultiPolygon")
    if not g.is_valid:
        g = g.buffer(0)
        g = g if isinstance(g, MultiPolygon) else MultiPolygon([g])
    return WKTElement(g.wkt, srid=SRID)


def latlng(geom: Any) -> tuple[float, float] | None:
    if geom is None:
        return None
    p = to_shape(geom)
    assert isinstance(p, Point)
    return (p.y, p.x)


def geojson(geom: Any) -> dict[str, Any] | None:
    if geom is None:
        return None
    return dict(mapping(to_shape(geom)))


def line_coords(geom: Any) -> list[list[float]] | None:
    """[[lng, lat], ...] for map rendering."""
    if geom is None:
        return None
    return [[round(x, 6), round(y, 6)] for x, y in to_shape(geom).coords]


def center(geom: Any) -> tuple[float, float] | None:
    if geom is None:
        return None
    c = to_shape(geom).centroid
    return (c.y, c.x)


def bbox(geom: Any) -> list[float] | None:
    if geom is None:
        return None
    return [round(v, 5) for v in to_shape(geom).bounds]
