"use client";

import { useCallback, useEffect, useState } from "react";
import { detectLang, type Key, type Lang, savedLang, saveLang, t } from "./i18n";

/** The reader's language: their saved choice, else the browser's, else English. */
export function useLang(
  preferred?: string | null,
): [Lang, (l: Lang) => void, (k: Key, v?: Record<string, string | number>) => string] {
  const [lang, setLang] = useState<Lang>("en");
  useEffect(() => {
    setLang(savedLang() ?? ((preferred as Lang | undefined) || detectLang()));
  }, [preferred]);
  const choose = useCallback((l: Lang) => {
    saveLang(l);
    setLang(l);
  }, []);
  const tr = useCallback((k: Key, v?: Record<string, string | number>) => t(lang, k, v), [lang]);
  return [lang, choose, tr];
}
