import type { ReactNode } from "react";
import { cn } from "@/lib/format";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-panel-2", className)} aria-hidden />;
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-line-strong bg-panel-2 px-1 font-mono text-[10px] text-muted">
      {children}
    </kbd>
  );
}

/** Line drawing for empty states: a calm horizon over still water. */
function StillWater() {
  return (
    <svg viewBox="0 0 120 64" className="h-16 w-28 text-line-strong" fill="none" aria-hidden="true">
      <circle cx="84" cy="22" r="9" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 40h104" stroke="currentColor" strokeWidth="1.5" />
      <path d="M20 48c6-3 10-3 16 0s10 3 16 0 10-3 16 0 10 3 16 0" stroke="currentColor" strokeWidth="1.5" />
      <path d="M34 56c5-2.5 8-2.5 13 0s8 2.5 13 0 8-2.5 13 0" stroke="currentColor" strokeWidth="1.5" opacity=".6" />
    </svg>
  );
}

export function Empty({
  title,
  body,
  action,
  className,
}: {
  title: string;
  body?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 px-6 py-14 text-center", className)}>
      <StillWater />
      <div>
        <p className="text-sm font-medium text-text">{title}</p>
        {body ? <p className="mx-auto mt-1 max-w-72 text-[13px] text-muted">{body}</p> : null}
      </div>
      {action}
    </div>
  );
}

export function ErrorNote({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 rounded-md border border-critical/40 bg-critical/10 px-3 py-2 text-[13px] text-text"
    >
      <span>{children}</span>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="shrink-0 font-medium text-accent-text hover:underline">
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Section({
  title,
  aside,
  children,
  className,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("space-y-2.5", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-text">{title}</h3>
        {aside ? <div className="text-xs text-muted">{aside}</div> : null}
      </div>
      {children}
    </section>
  );
}
