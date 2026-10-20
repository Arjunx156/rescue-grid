"use client";

import dynamic from "next/dynamic";

// the canvases need the DOM and real sizes; the page around them stays static
export const LandingReplay = dynamic(() => import("./replay-split").then((m) => m.ReplaySplit), {
  ssr: false,
  loading: () => (
    <div className="grid gap-8 md:grid-cols-2" aria-busy>
      {[0, 1].map((i) => (
        <div key={i} className="aspect-square rounded-xl border border-[#1f2937] bg-[#0b0f14]" />
      ))}
    </div>
  ),
});
