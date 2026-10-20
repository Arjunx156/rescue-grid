import type { Metadata } from "next";
import { type ReactNode, Suspense } from "react";
import { FieldShell } from "@/components/field/shell";

export const metadata: Metadata = { title: "Field", robots: { index: false } };

export default function FieldLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-white" />}>
      <FieldShell>{children}</FieldShell>
    </Suspense>
  );
}
