"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import {
  AttributionControl,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  Map as MlMap,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import type { AssignmentOut, CaseOut, DisasterOut, FloodZoneOut, PlanStop, TeamOut } from "@/lib/api";
import { LEVEL_LABEL, STATUS_LABEL } from "@/lib/format";
import { arrowImage, darkStyle, MAP_FONT_BOLD } from "@/lib/map-style";
import { useUi } from "@/lib/store";
import { clockLeft, frameDepths, type WaterField, waterFeatures } from "@/lib/water";

// the bundler moves MapLibre's code but not its worker; postinstall copies it to /public
if (typeof window !== "undefined") setWorkerUrl("/maplibre-gl-worker.mjs");

const LEVEL_COLORS = [
  "match",
  ["get", "level"],
  "critical",
  "#ef4444",
  "high",
  "#f97316",
  "medium",
  "#eab308",
  "#22c55e",
];
const FIELD_STATUSES = new Set(["assigned", "en_route", "on_scene"]);
// water depth in metres -> colour, the same ramp flat and in 3D
const WATER_RAMP = [
  "interpolate",
  ["linear"],
  ["get", "d"],
  0.05,
  "#155e75",
  0.5,
  "#0e7490",
  1,
  "#0891b2",
  2,
  "#22d3ee",
  3,
  "#a5f3fc",
];
const CLOCK_WINDOW_MIN = 180;

type FC = GeoJSON.FeatureCollection;
const empty: FC = { type: "FeatureCollection", features: [] };

function casesFC(cases: CaseOut[], levels: string[], now: number): FC {
  return {
    type: "FeatureCollection",
    features: cases
      .filter((c) => c.lat != null && c.lng != null && levels.includes(c.urgency_level))
      .map((c) => ({
        type: "Feature",
        id: c.id,
        geometry: {
          type: "Point",
          coordinates: [c.lng as number, c.lat as number],
        },
        properties: {
          id: c.id,
          level: c.urgency_level,
          score: c.urgency_score,
          people: c.people_count ?? 0,
          unsure: c.location_confidence < 0.6 ? 1 : 0,
          field: FIELD_STATUSES.has(c.status) ? 1 : 0,
          critical: c.urgency_level === "critical" ? 1 : 0,
          high: c.urgency_level === "high" ? 1 : 0,
          medium: c.urgency_level === "medium" ? 1 : 0,
          // minutes until the water reaches this family's danger line; -1 when it is not coming
          clock: FIELD_STATUSES.has(c.status) ? -1 : (clockLeft(c.water_clock, now) ?? -1),
        },
      })),
  };
}

function teamsFC(teams: TeamOut[]): FC {
  return {
    type: "FeatureCollection",
    features: teams
      .filter((t) => t.lat != null && t.lng != null)
      .map((t) => ({
        type: "Feature",
        id: t.id,
        geometry: {
          type: "Point",
          coordinates: [t.lng as number, t.lat as number],
        },
        properties: {
          id: t.id,
          call: t.call_sign,
          status: t.status,
          heading: t.heading ?? 0,
          asset: t.asset_type,
        },
      })),
  };
}

function routesFC(active: AssignmentOut[], proposed: PlanStop[]): FC {
  const line = (coords: number[][] | null | undefined, kind: string, id: string): GeoJSON.Feature | null =>
    coords && coords.length > 1
      ? {
          type: "Feature",
          geometry: { type: "LineString", coordinates: coords },
          properties: { kind, id },
        }
      : null;
  return {
    type: "FeatureCollection",
    features: [
      ...active.map((a) => line(a.route, "active", a.id)),
      ...proposed.filter((s) => s.status === "proposed").map((s) => line(s.route, "proposed", s.assignment_id)),
    ].filter((f): f is GeoJSON.Feature => f !== null),
  };
}

function floodFC(zones: FloodZoneOut[]): FC {
  return {
    type: "FeatureCollection",
    features: zones.map((z) => ({
      type: "Feature",
      geometry: z.geometry as unknown as GeoJSON.Geometry,
      properties: {
        depth: z.depth_estimate_m ?? 0.5,
        name: z.name ?? "Flood zone",
      },
    })),
  };
}

/** Built with text nodes: case text comes from the public and must never become HTML. */
function hoverCard(c: CaseOut): HTMLElement {
  const root = document.createElement("div");
  root.className = "space-y-1";
  const head = document.createElement("div");
  head.className = "flex items-center gap-2 text-[12px] font-medium";
  const level = document.createElement("span");
  level.textContent = `${LEVEL_LABEL[c.urgency_level] ?? c.urgency_level} ${c.urgency_score}`;
  level.style.color = `var(--${c.urgency_level})`;
  const code = document.createElement("span");
  code.className = "font-mono text-muted";
  code.textContent = c.tracking_code;
  head.append(level, code);
  const summary = document.createElement("div");
  summary.className = "text-[12px] text-text max-w-64";
  summary.textContent = c.summary ?? "";
  const where = document.createElement("div");
  where.className = "text-[11px] text-muted";
  where.textContent = [c.address_text ?? c.locality, STATUS_LABEL[c.status]].filter(Boolean).join(" · ");
  root.append(head, summary, where);
  return root;
}

export function CommandMap({
  disaster,
  cases,
  teams,
  assignments,
  proposed,
  flood,
  water,
  now,
}: {
  disaster: DisasterOut | undefined;
  cases: CaseOut[];
  teams: TeamOut[];
  assignments: AssignmentOut[];
  proposed: PlanStop[];
  flood: FloodZoneOut[];
  water: WaterField | null;
  now: number;
}) {
  const el = useRef<HTMLElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const fitted = useRef<string | null>(null);
  const { selectedCaseId, levels, showFlood, showTeams, showRoutes, pinEdit, flyTo } = useUi();
  const { showWater, waterFrame, waterWorst, map3d } = useUi();
  // clocks tick on the map every 15 seconds of the disaster's time: enough to watch them close
  const clockNow = Math.floor(now / 15_000) * 15_000;
  const byId = useMemo(() => new Map(cases.map((c) => [c.id, c])), [cases]);
  const byIdRef = useRef(byId);
  byIdRef.current = byId;

  // create once; the command layout keeps this alive across pages
  useEffect(() => {
    let cancelled = false;
    let pulse = 0;
    darkStyle()
      .then((style) => {
        if (cancelled || !el.current) return;
        const map = new MlMap({
          container: el.current,
          style,
          center: [80.2, 13.0],
          zoom: 10.5,
          attributionControl: false,
          dragRotate: false,
          pitchWithRotate: false,
          fadeDuration: 0,
        });
        mapRef.current = map;
        map.touchZoomRotate.disableRotation();
        map.addControl(new NavigationControl({ showCompass: false }), "bottom-left");
        map.addControl(new AttributionControl({ compact: true }), "bottom-left");
        map.on("load", () => {
          map.addImage("rg-arrow", arrowImage(), { sdf: true, pixelRatio: 2 });
          map.addSource("flood", { type: "geojson", data: empty });
          map.addSource("water", { type: "geojson", data: empty });
          map.addSource("routes", { type: "geojson", data: empty });
          map.addSource("teams", { type: "geojson", data: empty });
          map.addSource("cases", {
            type: "geojson",
            data: empty,
            cluster: true,
            clusterMaxZoom: 12,
            clusterRadius: 42,
            clusterProperties: {
              critical: ["+", ["get", "critical"]],
              high: ["+", ["get", "high"]],
              medium: ["+", ["get", "medium"]],
            },
          });
          map.addSource("pin", { type: "geojson", data: empty });

          map.addLayer({
            id: "flood-fill",
            type: "fill",
            source: "flood",
            paint: {
              "fill-color": "#22d3ee",
              "fill-opacity": ["interpolate", ["linear"], ["get", "depth"], 0.3, 0.05, 1, 0.1, 2, 0.17],
            },
          });
          map.addLayer({
            id: "flood-line",
            type: "line",
            source: "flood",
            paint: {
              "line-color": "#22d3ee",
              "line-opacity": 0.28,
              "line-width": 0.8,
            },
          });
          map.addLayer({
            id: "water-flat",
            type: "fill",
            source: "water",
            paint: {
              "fill-color": WATER_RAMP as never,
              "fill-opacity": ["interpolate", ["linear"], ["get", "d"], 0.05, 0.22, 1, 0.5, 2.5, 0.66],
            },
          });
          map.addLayer({
            id: "water-3d",
            type: "fill-extrusion",
            source: "water",
            layout: { visibility: "none" },
            paint: {
              "fill-extrusion-color": WATER_RAMP as never,
              // 120 m of column per metre of water: exaggerated so a street's depth reads at city scale
              "fill-extrusion-height": ["*", ["get", "d"], 120],
              "fill-extrusion-base": 0,
              "fill-extrusion-opacity": 0.82,
            },
          });
          map.addLayer({
            id: "routes-proposed",
            type: "line",
            source: "routes",
            filter: ["==", ["get", "kind"], "proposed"],
            layout: { "line-cap": "round", "line-join": "round" },
            paint: {
              "line-color": "#60a5fa",
              "line-width": 1.6,
              "line-opacity": 0.8,
              "line-dasharray": [1.5, 2],
            },
          });
          map.addLayer({
            id: "routes-active",
            type: "line",
            source: "routes",
            filter: ["==", ["get", "kind"], "active"],
            layout: { "line-cap": "round", "line-join": "round" },
            paint: {
              "line-color": "#3b82f6",
              "line-width": 2.6,
              "line-opacity": 0.95,
            },
          });
          map.addLayer({
            id: "clusters",
            type: "circle",
            source: "cases",
            filter: ["has", "point_count"],
            paint: {
              "circle-color": [
                "case",
                [">", ["get", "critical"], 0],
                "#ef4444",
                [">", ["get", "high"], 0],
                "#f97316",
                [">", ["get", "medium"], 0],
                "#eab308",
                "#22c55e",
              ],
              "circle-opacity": 0.22,
              "circle-stroke-color": [
                "case",
                [">", ["get", "critical"], 0],
                "#ef4444",
                [">", ["get", "high"], 0],
                "#f97316",
                [">", ["get", "medium"], 0],
                "#eab308",
                "#22c55e",
              ],
              "circle-stroke-width": 1.5,
              "circle-radius": ["step", ["get", "point_count"], 15, 10, 19, 50, 25, 200, 32],
            },
          });
          map.addLayer({
            id: "cluster-count",
            type: "symbol",
            source: "cases",
            filter: ["has", "point_count"],
            layout: {
              "text-field": ["get", "point_count_abbreviated"],
              "text-font": MAP_FONT_BOLD,
              "text-size": 12,
            },
            paint: { "text-color": "#e5e7eb" },
          });
          map.addLayer({
            id: "case-pulse",
            type: "circle",
            source: "cases",
            filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "level"], "critical"]],
            paint: {
              "circle-color": "#ef4444",
              "circle-opacity": 0,
              "circle-radius": 8,
              "circle-pitch-alignment": "map",
            },
          });
          map.addLayer({
            id: "case-clock",
            type: "circle",
            source: "cases",
            filter: [
              "all",
              ["!", ["has", "point_count"]],
              [">=", ["get", "clock"], 0],
              ["<=", ["get", "clock"], CLOCK_WINDOW_MIN],
            ],
            paint: {
              // the ring tightens as the water closes in, like the landing page's twin
              "circle-radius": ["interpolate", ["linear"], ["get", "clock"], 0, 10, CLOCK_WINDOW_MIN, 22],
              "circle-color": "transparent",
              "circle-stroke-color": ["case", ["<", ["get", "clock"], 60], "#ef4444", "#f97316"],
              "circle-stroke-width": 1.6,
              "circle-stroke-opacity": 0.9,
              "circle-pitch-alignment": "map",
            },
          });
          map.addLayer({
            id: "case-dots",
            type: "circle",
            source: "cases",
            filter: ["!", ["has", "point_count"]],
            paint: {
              "circle-color": LEVEL_COLORS as never,
              "circle-opacity": ["case", ["==", ["get", "unsure"], 1], 0.18, 0.92],
              "circle-radius": ["interpolate", ["linear"], ["get", "score"], 0, 4.5, 50, 6, 90, 8.5],
              "circle-stroke-width": ["case", ["==", ["get", "field"], 1], 2.5, ["==", ["get", "unsure"], 1], 1.6, 1],
              "circle-stroke-color": [
                "case",
                ["==", ["get", "field"], 1],
                "#3b82f6",
                ["==", ["get", "unsure"], 1],
                LEVEL_COLORS,
                "#0b0f14",
              ] as never,
            },
          });
          map.addLayer({
            id: "case-unsure",
            type: "symbol",
            source: "cases",
            filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "unsure"], 1]],
            layout: {
              "text-field": "?",
              "text-font": MAP_FONT_BOLD,
              "text-size": 10,
              "text-allow-overlap": true,
            },
            paint: { "text-color": "#e5e7eb" },
          });
          map.addLayer({
            id: "case-selected",
            type: "circle",
            source: "cases",
            filter: ["==", ["get", "id"], ""],
            paint: {
              "circle-color": "transparent",
              "circle-radius": 14,
              "circle-stroke-color": "#e5e7eb",
              "circle-stroke-width": 2,
            },
          });
          map.addLayer({
            id: "teams",
            type: "symbol",
            source: "teams",
            layout: {
              "icon-image": "rg-arrow",
              "icon-size": 0.95,
              "icon-rotate": ["get", "heading"],
              "icon-rotation-alignment": "map",
              "icon-allow-overlap": true,
              "text-field": ["get", "call"],
              "text-font": MAP_FONT_BOLD,
              "text-size": 10.5,
              "text-offset": [0, 1.45],
              "text-anchor": "top",
              "text-allow-overlap": true,
            },
            paint: {
              "icon-color": ["match", ["get", "status"], "off_duty", "#6b7280", "available", "#3b82f6", "#93c5fd"],
              "icon-halo-color": "#0b0f14",
              "icon-halo-width": 1.5,
              "text-color": ["match", ["get", "status"], "off_duty", "#6b7280", "#bfdbfe"],
              "text-halo-color": "#0b0f14",
              "text-halo-width": 1.4,
            },
          });
          map.addLayer({
            id: "pin",
            type: "circle",
            source: "pin",
            paint: {
              "circle-radius": 9,
              "circle-color": "#3b82f6",
              "circle-stroke-color": "#fff",
              "circle-stroke-width": 2,
            },
          });

          const popup = new Popup({
            closeButton: false,
            closeOnClick: false,
            offset: 12,
            className: "rg-popup",
          });
          map.on("mousemove", "case-dots", (e) => {
            const f = e.features?.[0] as MapGeoJSONFeature | undefined;
            const c = f ? byIdRef.current.get(String(f.properties.id)) : undefined;
            map.getCanvas().style.cursor = "pointer";
            if (c && f?.geometry.type === "Point") {
              popup
                .setLngLat(f.geometry.coordinates as [number, number])
                .setDOMContent(hoverCard(c))
                .addTo(map);
            }
          });
          map.on("mouseleave", "case-dots", () => {
            map.getCanvas().style.cursor = "";
            popup.remove();
          });
          map.on("click", "case-dots", (e) => {
            const id = e.features?.[0]?.properties?.id;
            if (id) useUi.getState().select(String(id));
          });
          map.on("click", "clusters", (e) => {
            const f = e.features?.[0];
            if (!f || f.geometry.type !== "Point") return;
            const center = f.geometry.coordinates as [number, number];
            (map.getSource("cases") as GeoJSONSource)
              .getClusterExpansionZoom(f.properties.cluster_id)
              .then((zoom) => map.easeTo({ center, zoom: zoom + 0.5 }))
              .catch(() => undefined);
          });
          for (const layer of ["clusters", "teams"]) {
            map.on("mouseenter", layer, () => {
              map.getCanvas().style.cursor = "pointer";
            });
            map.on("mouseleave", layer, () => {
              map.getCanvas().style.cursor = "";
            });
          }
          // a pin being corrected follows the pointer and lands where it is dropped
          map.on("click", (e) => {
            const edit = useUi.getState().pinEdit;
            if (edit) useUi.getState().movePin(e.lngLat.lat, e.lngLat.lng);
          });

          const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
          if (!reduce) {
            const start = performance.now();
            const tick = (t: number) => {
              const phase = ((t - start) % 1800) / 1800;
              if (map.getLayer("case-pulse")) {
                map.setPaintProperty("case-pulse", "circle-radius", 8 + phase * 18);
                map.setPaintProperty("case-pulse", "circle-opacity", 0.45 * (1 - phase));
              }
              pulse = requestAnimationFrame(tick);
            };
            pulse = requestAnimationFrame(tick);
          }
          setReady(true);
        });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      cancelAnimationFrame(pulse);
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("cases") as GeoJSONSource).setData(casesFC(cases, levels, clockNow));
  }, [ready, cases, levels, clockNow]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const data = showWater && water ? waterFeatures(water, frameDepths(water, waterFrame, waterWorst)) : empty;
    (map.getSource("water") as GeoJSONSource).setData(data);
  }, [ready, water, waterFrame, waterWorst, showWater]);

  // 3D: the water stands up as columns and the map tilts; 2D stays flat and north-up
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setLayoutProperty("water-flat", "visibility", map3d ? "none" : "visible");
    map.setLayoutProperty("water-3d", "visibility", map3d ? "visible" : "none");
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (map3d) {
      map.dragRotate.enable();
      map.easeTo({ pitch: 58, bearing: -18, duration: reduce ? 0 : 900 });
    } else {
      map.dragRotate.disable();
      map.easeTo({ pitch: 0, bearing: 0, duration: reduce ? 0 : 600 });
    }
  }, [ready, map3d]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("teams") as GeoJSONSource).setData(showTeams ? teamsFC(teams) : empty);
  }, [ready, teams, showTeams]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("routes") as GeoJSONSource).setData(showRoutes ? routesFC(assignments, proposed) : empty);
  }, [ready, assignments, proposed, showRoutes]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    // the live model replaces the static zones on screen; switch the water off to see the zones again
    const modelled = showWater && water != null;
    (map.getSource("flood") as GeoJSONSource).setData(showFlood && !modelled ? floodFC(flood) : empty);
  }, [ready, flood, showFlood, showWater, water]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("case-selected", ["==", ["get", "id"], selectedCaseId ?? ""]);
    const c = selectedCaseId ? byIdRef.current.get(selectedCaseId) : undefined;
    if (c?.lat != null && c.lng != null) {
      const bounds = map.getBounds();
      if (!bounds.contains([c.lng, c.lat]) || map.getZoom() < 12) {
        map.easeTo({
          center: [c.lng, c.lat],
          zoom: Math.max(map.getZoom(), 13.5),
          offset: [-180, 0],
          duration: 600,
        });
      }
    }
  }, [ready, selectedCaseId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("pin") as GeoJSONSource).setData(
      pinEdit
        ? {
            type: "FeatureCollection",
            features: [
              {
                type: "Feature",
                geometry: {
                  type: "Point",
                  coordinates: [pinEdit.lng, pinEdit.lat],
                },
                properties: {},
              },
            ],
          }
        : empty,
    );
    map.getCanvas().style.cursor = pinEdit ? "crosshair" : "";
  }, [ready, pinEdit]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !flyTo) return;
    map.easeTo({
      center: [flyTo.lng, flyTo.lat],
      zoom: flyTo.zoom ?? 14,
      duration: 700,
    });
  }, [ready, flyTo]);

  // frame the disaster once per disaster
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !disaster?.bbox || fitted.current === disaster.id) return;
    fitted.current = disaster.id;
    const [x1, y1, x2, y2] = disaster.bbox;
    map.fitBounds(
      [
        [x1, y1],
        [x2, y2],
      ],
      { padding: { top: 40, bottom: 40, left: 40, right: 420 }, duration: 0 },
    );
  }, [ready, disaster]);

  // the map is drawn behind panels that change size; keep it filling its box
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !el.current) return;
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el.current);
    return () => ro.disconnect();
  }, [ready]);

  const open = cases.length;
  return (
    <div className="absolute inset-0">
      <section
        ref={el}
        // MapLibre sets position: relative on its container, so size it explicitly
        className="h-full w-full"
        aria-label={`Map of ${open} open cases. Use the queue to move between cases with the keyboard.`}
      />
      {failed ? (
        <div className="absolute inset-0 grid place-items-center text-sm text-muted">
          The basemap could not load. Cases are still listed in the queue.
        </div>
      ) : null}
    </div>
  );
}
