"use client";

import Link from "next/link";
import { LANGS, type Lang } from "@/lib/i18n";
import { Logo } from "./logo";

export function PublicHeader({ lang, onLang, label }: { lang: Lang; onLang: (l: Lang) => void; label: string }) {
  return (
    <header className="mx-auto flex w-full max-w-xl items-center justify-between px-5 pt-[max(env(safe-area-inset-top),1rem)] pb-2">
      <Link href="/" className="inline-flex items-center gap-2 text-[15px] font-semibold">
        <Logo className="size-5 text-accent" />
        Rescue Grid
      </Link>
      <select
        value={lang}
        onChange={(e) => onLang(e.target.value as Lang)}
        aria-label={label}
        className="h-10 rounded-md border border-line-strong bg-bg px-2.5 font-native text-[15px]"
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code}>
            {l.name}
          </option>
        ))}
      </select>
    </header>
  );
}
