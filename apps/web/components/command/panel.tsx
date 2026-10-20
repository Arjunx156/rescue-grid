import type { ReactNode } from "react";
import { cn } from "@/lib/format";

/** A page that floats over the live map on the left, leaving the map in view. */
export function SidePanel({
  title,
  aside,
  toolbar,
  children,
  footer,
  label,
}: {
  title: string;
  aside?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  label?: string;
}) {
  return (
    <aside
      aria-label={label ?? title}
      className="glass absolute top-3 bottom-3 left-3 z-10 flex w-[460px] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-xl border border-line shadow-float"
    >
      <div className="space-y-3 border-b border-line px-4 pt-3.5 pb-3">
        <div className="flex items-center gap-2">
          <h1 className="text-[15px] font-semibold">{title}</h1>
          {aside ? <div className="ml-auto flex items-center gap-2 text-xs text-muted">{aside}</div> : null}
        </div>
        {toolbar}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">{children}</div>
      {footer ? <div className="border-t border-line px-4 py-3">{footer}</div> : null}
    </aside>
  );
}

/** A page that needs the whole canvas (tables, forms, charts) and covers the map. */
export function FullPage({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="absolute inset-0 z-10 overflow-y-auto bg-bg scroll-thin">
      <div className={cn("mx-auto max-w-[1400px] px-6 py-6", className)}>
        <div className="mb-6 flex flex-wrap items-end gap-4">
          <div>
            <h1 className="text-[20px] font-semibold tracking-tight">{title}</h1>
            {description ? <p className="mt-1 max-w-2xl text-[13px] text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="ml-auto flex items-center gap-2">{actions}</div> : null}
        </div>
        {children}
      </div>
    </div>
  );
}
