"use client";

import dynamic from "next/dynamic";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import type { TwinReadout } from "./flood-twin";

// three.js stays off the critical path: the headline paints first, the flood arrives after
const FloodTwin = dynamic(() => import("./flood-twin").then((m) => m.FloodTwin), { ssr: false });

const START = Date.UTC(2015, 11, 1, 12, 30); // 6 pm IST, 1 December 2015

function when(minute: number) {
  const d = new Date(START + minute * 60_000);
  const day = d.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "Asia/Kolkata",
  });
  const time = d.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  });
  return `${day}, ${time}`;
}

function Readout({ r }: { r: TwinReadout | null }) {
  if (!r) return null;
  return (
    <dl className="glass pointer-events-none rounded-lg border border-line px-4 py-3 font-mono text-[12px] leading-6 text-muted tnum">
      <div className="text-[13px] text-text">{when(r.minute)} IST</div>
      <div>
        <dt className="sr-only">Area under half a metre of water or more</dt>
        <dd>
          <span className="text-water">{r.floodedKm2}</span> km² under half a metre or more
        </dd>
      </div>
      <div>
        <dt className="sr-only">Families who have sent an SOS</dt>
        <dd>
          <span className="text-text">{r.reported}</span> families have asked for help
        </dd>
      </div>
      <div>
        <dt className="sr-only">Families the water reached, and how many a team reached first</dt>
        <dd>
          water reached <span className="text-critical">{r.atRisk}</span>, a team got there first for{" "}
          <span className="text-go">{r.beforeWater}</span>
        </dd>
      </div>
    </dl>
  );
}

/**
 * The flood, told by scrolling. The canvas sticks to the viewport while the beats scroll past;
 * the share of the section scrolled drives the clock and the camera. Beats are server-rendered.
 */
export function Story({ beats }: { beats: ReactNode[] }) {
  const section = useRef<HTMLElement>(null);
  const progress = useRef(0);
  const [readout, setReadout] = useState<TwinReadout | null>(null);
  const [failed, setFailed] = useState(false);
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const q = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(q.matches);
    const on = () => setReduced(q.matches);
    q.addEventListener("change", on);
    return () => q.removeEventListener("change", on);
  }, []);

  useEffect(() => {
    let raf = 0;
    const measure = () => {
      raf = 0;
      const el = section.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const span = rect.height - window.innerHeight;
      progress.current = Math.min(1, Math.max(0, -rect.top / Math.max(1, span)));
    };
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      cancelAnimationFrame(raf);
    };
  }, []);

  const onFail = useCallback(() => setFailed(true), []);

  return (
    <section ref={section} id="story" aria-label="The December 2015 flood, replayed" className="relative">
      <div className="sticky top-0 h-svh overflow-hidden">
        {failed ? (
          <div className="twin-fallback absolute inset-0" />
        ) : (
          <FloodTwin progress={progress} reduced={reduced} onReadout={setReadout} onFail={onFail} />
        )}
        {/* legibility, not decoration: the copy sits on the dark side of the frame */}
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,var(--bg)_0%,rgb(11_15_20/0.82)_34%,rgb(11_15_20/0)_62%)] max-md:bg-[linear-gradient(0deg,var(--bg)_0%,rgb(11_15_20/0.86)_45%,rgb(11_15_20/0.1)_75%)]" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-[linear-gradient(0deg,var(--bg),transparent)]" />
        <div className="absolute top-24 right-6 hidden lg:block" aria-live="off">
          <Readout r={readout} />
        </div>
      </div>
      <div className="relative -mt-[100svh]">
        {beats.map((beat, i) => (
          <div
            // beats are fixed at build time and never reorder
            // biome-ignore lint/suspicious/noArrayIndexKey: static content
            key={i}
            className="flex min-h-svh items-center px-6 max-md:items-end max-md:pb-20 md:px-12 lg:px-20"
          >
            <div className="max-w-xl">{beat}</div>
          </div>
        ))}
        <div className="h-[40svh]" aria-hidden="true" />
      </div>
    </section>
  );
}
