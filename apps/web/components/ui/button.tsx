import { Loader2 } from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/format";

type Variant = "primary" | "go" | "danger" | "outline" | "ghost" | "subtle";
type Size = "xs" | "sm" | "md" | "lg" | "xl";

const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-[#1d4ed8] active:bg-[#1e40af] border border-transparent",
  go: "bg-go text-go-ink hover:brightness-110 active:brightness-95 border border-transparent font-semibold",
  danger: "bg-transparent text-critical border border-critical/50 hover:bg-critical/10",
  outline: "bg-transparent text-text border border-line-strong hover:bg-panel-2",
  ghost: "bg-transparent text-muted hover:text-text hover:bg-panel-2 border border-transparent",
  subtle: "bg-panel-2 text-text border border-line hover:border-line-strong",
};

const SIZE: Record<Size, string> = {
  xs: "h-7 px-2 text-xs gap-1 rounded-md",
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-md",
  md: "h-9 px-3.5 text-sm gap-2 rounded-md",
  lg: "h-11 px-5 text-[15px] gap-2 rounded-md",
  // field app: one primary action, full width, easy to hit with a wet thumb
  xl: "h-14 px-6 text-lg gap-3 rounded-lg w-full",
};

interface Props extends ComponentProps<"button"> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export function buttonClass(variant: Variant = "primary", size: Size = "md", extra?: string) {
  return cn(
    "inline-flex items-center justify-center font-medium whitespace-nowrap select-none transition-[background,color,border,filter] duration-150 disabled:opacity-45 disabled:pointer-events-none",
    VARIANT[variant],
    SIZE[size],
    extra,
  );
}

export function Button({
  variant = "primary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: Props) {
  return (
    <button
      type="button"
      className={buttonClass(variant, size, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant = "primary",
  size = "md",
  className,
  children,
  icon,
  ...rest
}: ComponentProps<typeof Link> & {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)} {...rest}>
      {icon}
      {children}
    </Link>
  );
}

export function IconButton({ label, className, children, ...rest }: ComponentProps<"button"> & { label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-panel-2 hover:text-text disabled:opacity-40",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
