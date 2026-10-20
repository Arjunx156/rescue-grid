import type { Metadata } from "next";
import { type ReactNode, Suspense } from "react";
import { CommandShell } from "@/components/command/shell";

export const metadata: Metadata = { title: "Admin", robots: { index: false } };

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="theme-dark h-dvh bg-bg" />}>
      <CommandShell>{children}</CommandShell>
    </Suspense>
  );
}
