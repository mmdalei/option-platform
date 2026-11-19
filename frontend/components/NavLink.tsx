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
        "inline-flex min-h-10 items-center whitespace-nowrap rounded-md px-3 text-[14px] transition-colors duration-150 sm:text-[15px]",
        active
          ? "bg-ledger font-semibold text-ink shadow-[inset_0_-2px_0_0_#171C19]"
          : "font-medium text-ink-soft hover:bg-paper hover:text-ink active:bg-ledger",
      )}
    >
      {children}
    </Link>
  );
}