"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { type GeoJSONSource, Map as MlMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import { darkStyle } from "@/lib/map-style";

if (typeof window !== "undefined") setWorkerUrl("/maplibre-gl-worker.mjs");

const empty: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

/**
 * Outline an area by clicking its corners; click the first corner (or press Enter) to close it.
 * Existing shapes are shown underneath for reference.
 */
export function DrawMap({
  center,
  reference,
  onShape,
  className,
}: {
  center: [number, number] | null;
  reference: GeoJSON.Geometry[];
  onShape: (polygon: GeoJSON.Polygon | null) => void;
  className?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const [points, setPoints] = useState<[number, number][]>([]);
  const [closed, setClosed] = useState(false);
  const pointsRef = useRef(points);
  pointsRef.current = points;
  const closedRef = useRef(closed);
  closedRef.current = closed;

  useEffect(() => {
    let cancelled = false;
    darkStyle().then((style) => {
      if (cancelled || !el.current) return;
      const m = new MlMap({
        container: el.current,
        style,
        center: center ? [center[1], center[0]] : [80.2, 13.0],
        zoom: 10,
        dragRotate: false,
        doubleClickZoom: false,
      });
      map.current = m;
      m.addControl(new NavigationControl({ showCompass: false }), "top-right");
      m.on("load", () => {
        m.addSource("ref", { type: "geojson", data: empty });
        m.addSource("draft", { type: "geojson", data: empty });
        m.addLayer({
          id: "ref",
          type: "fill",
          source: "ref",
          paint: { "fill-color": "#22d3ee", "fill-opacity": 0.1 },
        });
        m.addLayer({
          id: "draft-fill",
          type: "fill",
          source: "draft",
          filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": "#3b82f6", "fill-opacity": 0.2 },
        });
        m.addLayer({
          id: "draft-line",
          type: "line",
          source: "draft",
          paint: { "line-color": "#60a5fa", "line-width": 2 },
        });
        m.addLayer({
          id: "draft-pts",
          type: "circle",
          source: "draft",
          filter: ["==", ["geometry-type"], "Point"],
          paint: {
            "circle-radius": 5,
            "circle-color": "#e5e7eb",
            "circle-stroke-color": "#3b82f6",
            "circle-stroke-width": 2,
          },
        });
        m.getCanvas().style.cursor = "crosshair";
        m.on("click", (e) => {
          if (closedRef.current) return;
          const pts = pointsRef.current;
          const p: [number, number] = [e.lngLat.lng, e.lngLat.lat];
          if (pts.length >= 3) {
            const first = m.project(pts[0]);
            if (Math.hypot(first.x - e.point.x, first.y - e.point.y) < 12) {
              setClosed(true);
              return;
            }
          }
          setPoints([...pts, p]);
        });
        setReady(true);
      });
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, [center]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    (m.getSource("ref") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: reference.map((g) => ({
        type: "Feature",
        geometry: g,
        properties: {},
      })),
    });
  }, [ready, reference]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const features: GeoJSON.Feature[] = points.map((p) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: p },
      properties: {},
    }));
    if (closed && points.length >= 3) {
      features.push({
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [[...points, points[0]]] },
        properties: {},
      });
    } else if (points.length >= 2) {
      features.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: points },
        properties: {},
      });
    }
    (m.getSource("draft") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features,
    });
    onShape(closed && points.length >= 3 ? { type: "Polygon", coordinates: [[...points, points[0]]] } : null);
  }, [ready, points, closed, onShape]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Enter" && pointsRef.current.length >= 3) setClosed(true);
      if (e.key === "Backspace" && !closedRef.current) setPoints((p) => p.slice(0, -1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="space-y-2">
      <div ref={el} className={className ?? "h-80 w-full overflow-hidden rounded-lg border border-line"} />
      <div className="flex items-center gap-3 text-xs text-muted">
        <span>
          {closed
            ? "Area closed."
            : points.length
              ? `${points.length} corners. Click the first corner or press Enter to close.`
              : "Click the map to place corners."}
        </span>
        {points.length ? (
          <button
            type="button"
            className="ml-auto text-accent-text hover:underline"
            onClick={() => {
              setPoints([]);
              setClosed(false);
            }}
          >
            Start over
          </button>
        ) : null}
      </div>
    </div>
  );
}
