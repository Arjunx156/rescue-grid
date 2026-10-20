import type { Metadata } from "next";
import { Suspense } from "react";
import { InviteForm } from "./invite-form";

export const metadata: Metadata = {
  title: "Accept your invite",
  robots: { index: false },
};

export default function InvitePage() {
  return (
    <Suspense fallback={<div className="min-h-dvh bg-bg" />}>
      <InviteForm />
    </Suspense>
  );
}
