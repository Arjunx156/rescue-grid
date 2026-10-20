import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/format";

const control =
  "w-full rounded-md border border-line-strong bg-bg px-3 text-sm text-text placeholder:text-faint transition-colors hover:border-faint focus:border-focus focus:outline-none focus-visible:outline-none focus:ring-2 focus:ring-focus/30 disabled:opacity-50 aria-invalid:border-critical";

export function Input({ className, ...rest }: ComponentProps<"input">) {
  return <input className={cn(control, "h-9", className)} {...rest} />;
}

export function Textarea({ className, ...rest }: ComponentProps<"textarea">) {
  return <textarea className={cn(control, "min-h-24 py-2 leading-relaxed", className)} {...rest} />;
}

export function Select({ className, children, ...rest }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        control,
        "h-9 appearance-none bg-[length:16px] pr-8",
        "bg-[right_0.6rem_center] bg-no-repeat",
        className,
      )}
      style={{
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
      }}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Label({ className, ...rest }: ComponentProps<"label">) {
  // biome-ignore lint/a11y/noLabelWithoutControl: callers pass htmlFor or wrap the control
  return <label className={cn("block text-[13px] font-medium text-text", className)} {...rest} />;
}

export function FormRow({
  label,
  hint,
  error,
  htmlFor,
  large,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  htmlFor: string;
  /** public forms read on a phone in a crisis: bigger labels */
  large?: boolean;
  children: ReactNode;
}) {
  return (
    <div className={large ? "space-y-2" : "space-y-1.5"}>
      <Label htmlFor={htmlFor} className={large ? "text-[15px]" : undefined}>
        {label}
      </Label>
      {children}
      {error ? (
        <p className={cn("text-critical", large ? "text-[13px]" : "text-xs")} role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className={cn("text-muted", large ? "text-[13px]" : "text-xs")}>{hint}</p>
      ) : null}
    </div>
  );
}
