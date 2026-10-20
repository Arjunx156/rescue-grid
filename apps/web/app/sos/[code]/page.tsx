import type { Metadata } from "next";
import { Suspense } from "react";
import { Tracker } from "./tracker";

export const metadata: Metadata = {
  title: "Your request",
  robots: { index: false },
};

export default function TrackerPage() {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-white" />}>
      <Tracker />
    </Suspense>
  );
}
