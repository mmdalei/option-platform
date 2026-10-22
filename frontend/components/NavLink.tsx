"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export default function NavLink({ href, children }: { href: string; children: ReactNode }) {
  const pathname = usePathname();
  const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "border-b-2 py-1 text-[15px]",
        active ? "border-ink font-semibold" : "border-transparent text-ink-soft hover:text-ink",
      )}
    >
      {children}
    </Link>
  );
}
