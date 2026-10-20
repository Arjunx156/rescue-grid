"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { type GeoJSONSource, LngLatBounds, Map as MlMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import type { FloodZoneOut } from "@/lib/api";
import { arrowImage, LIGHT_STYLE_URL, MAP_FONT_BOLD } from "@/lib/map-style";

if (typeof window !== "undefined") setWorkerUrl("/maplibre-gl-worker.mjs");

const LEVEL: Record<string, string> = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#ca8a04",
  low: "#16a34a",
};
const empty: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

export interface FieldStop {
  lat: number;
  lng: number;
  level: string;
  label: string;
}

/** The crew's map: where we are, where they are, how to get there. Light for sunlight. */
export function FieldMap({
  me,
  heading,
  stops,
  route,
  flood,
  className,
}: {
  me: { lat: number; lng: number } | null;
  heading?: number | null;
  stops: FieldStop[];
  route: number[][] | null;
  flood: FloodZoneOut[];
  className?: string;
}) {
  const el = useRef<HTMLElement>(null);
  const map = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const framed = useRef(false);

  useEffect(() => {
    if (!el.current) return;
    const m = new MlMap({
      container: el.current,
      style: LIGHT_STYLE_URL,
      center: [80.22, 13.0],
      zoom: 11,
      dragRotate: false,
      attributionControl: { compact: true },
    });
    map.current = m;
    m.touchZoomRotate.disableRotation();
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      m.addImage("rg-arrow", arrowImage(), { sdf: true, pixelRatio: 2 });
      m.addSource("flood", { type: "geojson", data: empty });
      m.addSource("route", { type: "geojson", data: empty });
      m.addSource("stops", { type: "geojson", data: empty });
      m.addSource("me", { type: "geojson", data: empty });
      m.addLayer({
        id: "flood",
        type: "fill",
        source: "flood",
        paint: { "fill-color": "#0891b2", "fill-opacity": 0.12 },
      });
      m.addLayer({
        id: "route-casing",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#ffffff", "line-width": 8 },
      });
      m.addLayer({
        id: "route",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#2563eb", "line-width": 4.5 },
      });
      m.addLayer({
        id: "stops",
        type: "circle",
        source: "stops",
        paint: {
          "circle-radius": 10,
          "circle-color": ["get", "color"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 3,
        },
      });
      m.addLayer({
        id: "stop-labels",
        type: "symbol",
        source: "stops",
        layout: {
          "text-field": ["get", "label"],
          "text-font": MAP_FONT_BOLD,
          "text-size": 12,
          "text-offset": [0, 1.6],
          "text-anchor": "top",
        },
        paint: {
          "text-color": "#111827",
          "text-halo-color": "#ffffff",
          "text-halo-width": 2,
        },
      });
      m.addLayer({
        id: "me",
        type: "symbol",
        source: "me",
        layout: {
          "icon-image": "rg-arrow",
          "icon-size": 1.2,
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          "icon-allow-overlap": true,
        },
        paint: {
          "icon-color": "#2563eb",
          "icon-halo-color": "#ffffff",
          "icon-halo-width": 2,
        },
      });
      setReady(true);
    });
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    (m.getSource("flood") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: flood.map((z) => ({
        type: "Feature",
        geometry: z.geometry as unknown as GeoJSON.Geometry,
        properties: {},
      })),
    });
    (m.getSource("route") as GeoJSONSource).setData(
      route && route.length > 1
        ? {
            type: "Feature",
            geometry: { type: "LineString", coordinates: route },
            properties: {},
          }
        : empty,
    );
    (m.getSource("stops") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: stops.map((s) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [s.lng, s.lat] },
        properties: { color: LEVEL[s.level] ?? "#6b7280", label: s.label },
      })),
    });
    (m.getSource("me") as GeoJSONSource).setData(
      me
        ? {
            type: "Feature",
            geometry: { type: "Point", coordinates: [me.lng, me.lat] },
            properties: { heading: heading ?? 0 },
          }
        : empty,
    );
    if (!framed.current && (me || stops.length)) {
      framed.current = true;
      const b = new LngLatBounds();
      if (me) b.extend([me.lng, me.lat]);
      for (const s of stops) b.extend([s.lng, s.lat]);
      m.fitBounds(b, { padding: 60, maxZoom: 15, duration: 0 });
    }
  }, [ready, me, heading, stops, route, flood]);

  return <section ref={el} className={className ?? "h-full w-full"} aria-label="Map of your assignment" />;
}
