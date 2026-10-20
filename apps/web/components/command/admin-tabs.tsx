"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/format";

export function AdminTabs() {
  const path = usePathname();
  return (
    <nav aria-label="Admin" className="mb-6 flex gap-1 border-b border-line">
      {[
        ["/admin/disasters", "Disasters"],
        ["/admin/users", "People"],
      ].map(([href, label]) => (
        <Link
          key={href}
          href={href}
          aria-current={path === href ? "page" : undefined}
          className={cn(
            "-mb-px border-b-2 px-3 py-2 text-[13px]",
            path === href ? "border-accent text-text" : "border-transparent text-muted hover:text-text",
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
