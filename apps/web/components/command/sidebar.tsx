"use client";

import {
  BarChart3,
  ClipboardCheck,
  FileInput,
  History,
  ListOrdered,
  Map as MapIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Route,
  Settings,
  Shield,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cn } from "@/lib/format";
import { Logo } from "../logo";
import { Tip } from "../ui/overlay";

const NAV = [
  { href: "/command", label: "Map", icon: MapIcon, key: "m" },
  { href: "/command/queue", label: "Queue", icon: ListOrdered, key: "q" },
  {
    href: "/command/review",
    label: "Review",
    icon: ClipboardCheck,
    key: "r",
    count: "review",
  },
  { href: "/command/teams", label: "Teams", icon: Users, key: "t" },
  {
    href: "/command/dispatch",
    label: "Dispatch",
    icon: Route,
    key: "d",
    count: "dispatch",
  },
  { href: "/command/intake", label: "Intake", icon: FileInput, key: "i" },
  { href: "/command/analytics", label: "Analytics", icon: BarChart3, key: "a" },
  { href: "/command/replay", label: "Replay", icon: History, key: "p" },
] as const;

export function Sidebar({ counts, isAdmin }: { counts: { review: number; dispatch: number }; isAdmin: boolean }) {
  const path = usePathname();
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    try {
      setNarrow(localStorage.getItem("rg:nav") === "narrow");
    } catch {
      /* private mode */
    }
  }, []);
  const toggle = () => {
    setNarrow((v) => {
      try {
        localStorage.setItem("rg:nav", v ? "wide" : "narrow");
      } catch {
        /* private mode */
      }
      return !v;
    });
  };
  const active = (href: string) =>
    href === "/command" ? path === "/command" || path.startsWith("/command/cases") : path.startsWith(href);
  const item = (href: string, label: string, Icon: typeof MapIcon, count?: number) => {
    const link = (
      <Link
        href={href}
        aria-current={active(href) ? "page" : undefined}
        className={cn(
          "group relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13px] transition-colors",
          active(href) ? "bg-panel-2 text-text" : "text-muted hover:bg-panel-2/60 hover:text-text",
          narrow && "justify-center px-0",
        )}
      >
        <Icon className={cn("size-4 shrink-0", active(href) && "text-accent-text")} aria-hidden />
        {narrow ? <span className="sr-only">{label}</span> : <span className="truncate">{label}</span>}
        {count ? (
          <span
            className={cn(
              "tnum text-[11px] text-muted",
              narrow ? "absolute -top-0.5 right-0.5 rounded-full bg-accent px-1 text-[10px] text-white" : "ml-auto",
            )}
          >
            {count > 99 ? "99+" : count}
          </span>
        ) : null}
      </Link>
    );
    return narrow ? (
      <Tip key={href} label={label} side="right">
        {link}
      </Tip>
    ) : (
      <div key={href}>{link}</div>
    );
  };
  return (
    <nav
      aria-label="Command centre"
      className={cn(
        "flex h-dvh flex-col border-r border-line bg-bg py-3 transition-[width] duration-200",
        narrow ? "w-14 px-2" : "w-52 px-3",
      )}
    >
      <Link href="/command" className={cn("mb-5 flex h-8 items-center gap-2 px-1.5", narrow && "justify-center px-0")}>
        <Logo className="size-5 text-signal" />
        {narrow ? null : <span className="text-[14px] font-semibold tracking-tight">Rescue Grid</span>}
      </Link>
      <div className="space-y-0.5">
        {NAV.map((n) => item(n.href, n.label, n.icon, "count" in n ? counts[n.count] : undefined))}
      </div>
      <div className="mt-auto space-y-0.5">
        {isAdmin ? item("/admin/disasters", "Admin", Shield) : null}
        {item("/settings", "Settings", Settings)}
        <button
          type="button"
          onClick={toggle}
          className={cn(
            "flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-[13px] text-muted hover:bg-panel-2/60 hover:text-text",
            narrow && "justify-center px-0",
          )}
          aria-label={narrow ? "Expand sidebar" : "Collapse sidebar"}
        >
          {narrow ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          {narrow ? null : "Collapse"}
        </button>
      </div>
    </nav>
  );
}

export const NAV_KEYS = NAV.map((n) => ({
  key: n.key,
  href: n.href,
  label: n.label,
}));
