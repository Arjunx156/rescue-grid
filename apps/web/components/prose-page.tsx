import Link from "next/link";
import type { ReactNode } from "react";
import { Logo } from "./logo";

export const CONTACT_EMAIL = process.env.CONTACT_EMAIL || null;

/** A plain reading page for policies: one column, generous measure, nothing else on screen. */
export function ProsePage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <div className="min-h-dvh bg-bg text-text">
      <header className="mx-auto w-full max-w-2xl px-6 pt-8">
        <Link href="/" className="inline-flex items-center gap-2 text-[15px] font-semibold">
          <Logo className="size-5 text-accent" />
          Rescue Grid
        </Link>
      </header>
      <main className="mx-auto w-full max-w-2xl px-6 pt-14 pb-24">
        <h1 className="text-[36px] leading-tight font-semibold tracking-[-0.02em]">{title}</h1>
        <p className="mt-3 text-[14px] text-muted">Last updated {updated}</p>
        <div className="mt-10 text-[16px] leading-relaxed text-muted [&_a]:text-accent-text [&_a]:underline [&_a]:underline-offset-2 [&_h2]:mt-12 [&_h2]:mb-3 [&_h2]:text-[20px] [&_h2]:font-semibold [&_h2]:text-text [&_li]:mt-2 [&_p]:mt-4 [&_strong]:font-medium [&_strong]:text-text [&_ul]:mt-4 [&_ul]:list-disc [&_ul]:pl-5">
          {children}
        </div>
      </main>
    </div>
  );
}

export function Contact() {
  return CONTACT_EMAIL ? (
    <>
      write to <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
    </>
  ) : (
    <>contact the organisation that runs this service in your area</>
  );
}
