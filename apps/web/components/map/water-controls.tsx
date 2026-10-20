"use client";

import { Pause, Play, Waves } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import type { WaterOut } from "@/lib/api";
import { ago, clock, cn } from "@/lib/format";
import { useUi } from "@/lib/store";
import type { WaterField } from "@/lib/water";

const PLAY_MS = 7000; // the whole three hours, played through

function Toggle({
  on,
  onClick,
  children,
  label,
}: {
  on: boolean;
  onClick: () => void;
  children: ReactNode;
  label?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={label}
      onClick={onClick}
      className={cn(
        "h-7 rounded-md px-2.5 text-[12px] font-medium transition-colors duration-150",
        on ? "bg-panel-2 text-text" : "text-muted hover:text-text",
      )}
    >
      {children}
    </button>
  );
}

/**
 * The forecast on the map: scrub the next three hours, play them, flip between the likely and
 * the worst case, stand the water up in 3D. Says plainly when there is no model to show.
 */
export function WaterControls({
  water,
  field,
  now,
}: {
  water: WaterOut | undefined;
  field: WaterField | null;
  now: number;
}) {
  const { showWater, waterFrame, waterWorst, map3d, setLayer, setWaterFrame, setWaterWorst, setMap3d } = useUi();
  const [playing, setPlaying] = useState(false);
  const last = field ? field.frames - 1 : 0;

  useEffect(() => {
    if (!playing || !field) return;
    let raf = 0;
    const from = performance.now();
    // read once, when play is pressed: playing on from where the slider was left
    const current = useUi.getState().waterFrame;
    const start = current >= last ? 0 : current;
    const tick = (t: number) => {
      const f = start + ((t - from) / PLAY_MS) * last;
      if (f >= last) {
        setWaterFrame(last);
        setPlaying(false);
        return;
      }
      setWaterFrame(f);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, field, last, setWaterFrame]);

  if (!water) return null;
  if (!water.available || !field) {
    return (
      <div className="glass flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[12px] text-muted shadow-float">
        <Waves className="size-4 text-water" aria-hidden="true" />
        <span>Water clock off. {water.reason ?? "No forecast yet."}</span>
      </div>
    );
  }

  const at = field.issuedAt + waterFrame * field.everyMin * 60_000;
  const age = ago(new Date(field.issuedAt), now);
  const ahead = Math.round(waterFrame * field.everyMin);
  return (
    <section
      aria-label="Flood forecast"
      className="glass w-[min(560px,calc(100vw-2rem))] rounded-xl border border-line px-4 pt-3 pb-3.5 shadow-float"
    >
      <div className="flex items-center gap-3">
        <button
          type="button"
          aria-pressed={showWater}
          onClick={() => setLayer("showWater", !showWater)}
          className="inline-flex items-center gap-1.5 text-[13px] font-semibold"
        >
          <Waves className={cn("size-4", showWater ? "text-water" : "text-faint")} aria-hidden="true" />
          Water
        </button>
        <span className="truncate text-[12px] text-muted">
          {age === "now" ? "Forecast just now" : `Forecast ${age} ago`}, from{" "}
          {field.reportsUsed.toLocaleString("en-IN")} reports
        </span>
        <div className="ml-auto flex items-center gap-0.5 rounded-lg border border-line p-0.5">
          <Toggle on={!map3d} onClick={() => setMap3d(false)} label="Flat map">
            2D
          </Toggle>
          <Toggle on={map3d} onClick={() => setMap3d(true)} label="Tilt the map and stand the water up">
            3D
          </Toggle>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pause the forecast" : "Play the next three hours"}
          className="grid size-8 shrink-0 place-items-center rounded-full border border-line-strong text-text hover:bg-panel-2"
        >
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5 translate-x-px" />}
        </button>
        <input
          type="range"
          min={0}
          max={last}
          step={0.05}
          value={waterFrame}
          onChange={(e) => {
            setPlaying(false);
            setWaterFrame(Number(e.target.value));
          }}
          aria-label="Forecast time"
          aria-valuetext={ahead ? `${clock(new Date(at))}, ${ahead} minutes ahead` : "Now"}
          className="h-1 flex-1 cursor-pointer accent-[#22d3ee]"
        />
        <span className="w-[7.5rem] shrink-0 text-right font-mono text-[12px] text-muted tnum">
          {ahead ? (
            <>
              <span className="text-text">{clock(new Date(at))}</span> +{ahead}m
            </>
          ) : (
            <span className="text-text">Now</span>
          )}
        </span>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <div className="flex items-center gap-0.5 rounded-lg border border-line p-0.5">
          <Toggle on={!waterWorst} onClick={() => setWaterWorst(false)}>
            Likely
          </Toggle>
          <Toggle on={waterWorst} onClick={() => setWaterWorst(true)}>
            Worst case
          </Toggle>
        </div>
        <div className="ml-auto flex items-center gap-2 text-[11px] text-muted tnum" aria-hidden="true">
          <span>0.3</span>
          <span className="h-2 w-28 rounded-full bg-[linear-gradient(90deg,#155e75,#0891b2,#22d3ee,#a5f3fc)]" />
          <span>3 m</span>
        </div>
      </div>
    </section>
  );
}
