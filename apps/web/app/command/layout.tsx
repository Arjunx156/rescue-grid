import type { Metadata } from "next";
import { type ReactNode, Suspense } from "react";
import { CommandShell } from "@/components/command/shell";

export const metadata: Metadata = {
  title: "Command centre",
  robots: { index: false },
};

export default function CommandLayout({ children }: { children: ReactNode }) {
  // live, per-user and clock-driven: nothing here belongs in a prerendered shell
  return (
    <Suspense fallback={<div className="theme-dark h-dvh bg-bg" />}>
      <CommandShell>{children}</CommandShell>
    </Suspense>
  );
}
