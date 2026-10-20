"use client";

import { CheckCircle2, CircleAlert, Info, Siren, X } from "lucide-react";
import { useEffect } from "react";
import { cn } from "@/lib/format";
import { type Toast, useUi } from "@/lib/store";

const ICON = {
  critical: <Siren className="size-4 text-critical" />,
  rescued: <CheckCircle2 className="size-4 text-go" />,
  success: <CheckCircle2 className="size-4 text-go" />,
  error: <CircleAlert className="size-4 text-critical" />,
  info: <Info className="size-4 text-accent-text" />,
};

function Item({ t }: { t: Toast }) {
  const { dismiss, select } = useUi();
  useEffect(() => {
    const ms = t.undo ? 8000 : t.kind === "critical" ? 8000 : t.kind === "rescued" ? 3500 : 5000;
    const timer = setTimeout(() => dismiss(t.id), ms);
    return () => clearTimeout(timer);
  }, [t, dismiss]);
  return (
    <div
      role={t.kind === "critical" || t.kind === "error" ? "alert" : "status"}
      className={cn(
        "glass pointer-events-auto flex w-[22rem] max-w-[calc(100vw-2rem)] items-start gap-3 rounded-lg border px-3.5 py-3 text-[13px] text-text shadow-float animate-in",
        t.kind === "critical" ? "border-critical/50" : "border-line",
      )}
    >
      <span className="mt-0.5">{ICON[t.kind]}</span>
      <div className="min-w-0 flex-1">
        <p className="leading-snug">{t.text}</p>
        <div className="mt-1.5 flex gap-3 empty:hidden">
          {t.caseId ? (
            <button
              type="button"
              className="font-medium text-accent-text hover:underline"
              onClick={() => {
                select(t.caseId ?? null);
                dismiss(t.id);
              }}
            >
              Open case
            </button>
          ) : null}
          {t.undo ? (
            <button
              type="button"
              className="font-medium text-accent-text hover:underline"
              onClick={() => {
                t.undo?.();
                dismiss(t.id);
              }}
            >
              Undo
            </button>
          ) : null}
        </div>
      </div>
      <button type="button" aria-label="Dismiss" className="text-muted hover:text-text" onClick={() => dismiss(t.id)}>
        <X className="size-3.5" />
      </button>
    </div>
  );
}

export function Toasts() {
  const toasts = useUi((s) => s.toasts);
  return (
    <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-4 z-[60] flex flex-col items-end gap-2">
      {toasts.map((t) => (
        <Item key={t.id} t={t} />
      ))}
    </div>
  );
}
