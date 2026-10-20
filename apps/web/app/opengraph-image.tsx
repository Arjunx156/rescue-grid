import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const alt = "Rescue Grid: thousands of SOS messages, one live rescue plan";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const INK = "#e5e7eb";
const MUTED = "#9ca3af";
const SIGNAL = "#3b82f6";

// a still of the command map: streets, a flood corridor, pins and one team on its way
function MapStill() {
  const streets = [70, 150, 230, 310, 390];
  return (
    <svg
      aria-hidden="true"
      width="460"
      height="420"
      viewBox="0 0 460 420"
      style={{ position: "absolute", right: 72, top: 105 }}
    >
      <rect width="460" height="420" rx="24" fill="#0e141c" stroke="#1f2937" />
      {streets.map((v) => (
        <path key={`h${v}`} d={`M0 ${v}H460`} stroke="#18202c" strokeWidth="2" />
      ))}
      {streets.map((v) => (
        <path key={`v${v}`} d={`M${v + 20} 0V420`} stroke="#18202c" strokeWidth="2" />
      ))}
      <path
        d="M-10 330 C 90 300, 140 220, 230 210 S 380 120, 470 90"
        fill="none"
        stroke="#22d3ee"
        strokeOpacity="0.14"
        strokeWidth="64"
        strokeLinecap="round"
      />
      <path d="M90 360 L 170 300 L 262 238" fill="none" stroke={SIGNAL} strokeWidth="4" strokeDasharray="10 8" />
      <path d="M90 372 l -12 18 h 24 z" fill={SIGNAL} />
      <circle cx="262" cy="238" r="24" fill="#ef4444" fillOpacity="0.18" />
      <circle cx="262" cy="238" r="10" fill="#ef4444" />
      <circle cx="350" cy="140" r="9" fill="#f97316" />
      <circle cx="160" cy="150" r="8" fill="#eab308" />
      <circle cx="390" cy="300" r="8" fill="#22c55e" />
      <circle cx="120" cy="250" r="8" fill="#22c55e" />
    </svg>
  );
}

export default async function OpengraphImage() {
  const fonts = join(process.cwd(), "node_modules/@fontsource/inter/files");
  const [regular, semibold] = await Promise.all([
    readFile(join(fonts, "inter-latin-400-normal.woff")),
    readFile(join(fonts, "inter-latin-600-normal.woff")),
  ]);
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        background: "#0b0f14",
        color: INK,
        padding: 72,
        position: "relative",
        fontFamily: "Inter",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", width: 560 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 30, fontWeight: 600 }}>
          <svg aria-hidden="true" width="36" height="36" viewBox="0 0 24 24" fill="none">
            <path d="M3 8h18M3 16h18M8 3v18M16 3v18" stroke={SIGNAL} strokeOpacity=".45" strokeWidth="1.5" />
            <circle cx="16" cy="8" r="3.2" fill={SIGNAL} />
            <circle cx="16" cy="8" r="5.6" stroke={SIGNAL} strokeWidth="1.2" strokeOpacity=".6" />
          </svg>
          Rescue Grid
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ fontSize: 62, fontWeight: 600, lineHeight: 1.06, letterSpacing: -2 }}>
            Thousands of SOS messages. One live rescue plan.
          </div>
          <div style={{ marginTop: 26, fontSize: 26, color: MUTED, lineHeight: 1.4 }}>
            Read in five languages, pinned to a street, merged, ranked and dispatched.
          </div>
        </div>
      </div>
      <MapStill />
    </div>,
    {
      ...size,
      fonts: [
        { name: "Inter", data: regular, weight: 400, style: "normal" },
        { name: "Inter", data: semibold, weight: 600, style: "normal" },
      ],
    },
  );
}
