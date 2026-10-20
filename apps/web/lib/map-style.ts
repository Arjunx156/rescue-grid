import type { StyleSpecification } from "maplibre-gl";

/**
 * Basemaps from OpenFreeMap (free, no key, OSM data). The command centre's dark map is
 * re-tinted to the product's navy so the data, not the streets, carries the colour.
 */
const DARK_URL = process.env.NEXT_PUBLIC_MAP_STYLE_DARK || "https://tiles.openfreemap.org/styles/dark";
export const LIGHT_STYLE_URL =
  process.env.NEXT_PUBLIC_MAP_STYLE_LIGHT || "https://tiles.openfreemap.org/styles/positron";

const PAINT: Record<string, Record<string, unknown>> = {
  background: { "background-color": "#0b0f14" },
  water: { "fill-color": "#0c1a24" },
  waterway: { "line-color": "#123446" },
  landuse_park: { "fill-color": "#0d1511", "fill-opacity": 0.7 },
  landcover_wood: { "fill-color": "#0d1511", "fill-opacity": 0.6 },
  landuse_residential: { "fill-color": "#0e131a", "fill-opacity": 0.6 },
  building: { "fill-color": "#111822", "fill-opacity": 0.75 },
  "aeroway-area": { "fill-color": "#121923" },
  "aeroway-runway": { "line-color": "#18202b" },
  "aeroway-taxiway": { "line-color": "#151c26" },
  highway_minor: { "line-color": "#18202c" },
  highway_path: { "line-color": "#151c26" },
  highway_major_casing: { "line-color": "#0b0f14" },
  highway_major_inner: { "line-color": "#212b39" },
  highway_major_subtle: { "line-color": "#1b2431" },
  highway_motorway_casing: { "line-color": "#0b0f14" },
  highway_motorway_inner: { "line-color": "#283445" },
  highway_motorway_subtle: { "line-color": "#202a38" },
  railway: { "line-color": "#1c2532" },
  railway_dashline: { "line-color": "#0b0f14" },
  railway_minor: { "line-color": "#19212d" },
  boundary_state: { "line-color": "#2a3647" },
  "boundary_country_z5-": { "line-color": "#2a3647" },
};

const TEXT: Record<string, string> = {
  water_name: "#2b6f8a",
  highway_name_motorway: "#6b7280",
  highway_name_other: "#5b6573",
};

let cached: Promise<StyleSpecification> | null = null;

export function darkStyle(): Promise<StyleSpecification> {
  cached ??= fetch(DARK_URL)
    .then((r) => r.json() as Promise<StyleSpecification>)
    .then((style) => {
      for (const layer of style.layers) {
        const paint = PAINT[layer.id];
        if (paint) layer.paint = { ...(layer.paint ?? {}), ...paint } as never;
        if (layer.type === "symbol") {
          const color = TEXT[layer.id] ?? (layer.id.startsWith("place_") ? "#8b95a3" : undefined);
          if (color) {
            layer.paint = {
              ...(layer.paint ?? {}),
              "text-color": color,
              "text-halo-color": "#0b0f14",
              "text-halo-width": 1.2,
            } as never;
          }
        }
      }
      return style;
    })
    .catch((e) => {
      cached = null;
      throw e;
    });
  return cached;
}

/** Text font present in OpenFreeMap's glyph server. */
export const MAP_FONT = ["Noto Sans Regular"];
export const MAP_FONT_BOLD = ["Noto Sans Bold"];

export const ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>';

/** A small upward arrow, drawn once and recoloured by MapLibre (SDF). */
export function arrowImage(size = 44): {
  width: number;
  height: number;
  data: Uint8ClampedArray;
} {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("no 2d context");
  const s = size / 44;
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.moveTo(22 * s, 4 * s);
  ctx.lineTo(37 * s, 38 * s);
  ctx.lineTo(22 * s, 30 * s);
  ctx.lineTo(7 * s, 38 * s);
  ctx.closePath();
  ctx.fill();
  const img = ctx.getImageData(0, 0, size, size);
  return { width: size, height: size, data: img.data };
}
