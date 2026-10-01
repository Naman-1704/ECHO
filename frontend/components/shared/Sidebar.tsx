"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { EchoWordmark } from "@/components/shared/EchoWordmark";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/projects", label: "Projects" },
  { href: "/dashboard/people", label: "People" },
  { href: "/chat", label: "Ask Echo" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { logout } = useAuth();

  return (
    <aside className="sidebar-reveal w-56 shrink-0 border-r border-line bg-paper flex flex-col h-screen sticky top-0">
      <div className="px-6 pt-8 pb-6">
        <EchoWordmark size="compact" />
        <p className="text-xs text-stone-light mt-1 leading-snug">
          Employee Context &amp; Handoff Orchestrator
        </p>
      </div>

      <nav className="flex-1 px-3">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`relative block pl-4 pr-3 py-2 mb-0.5 text-sm transition-colors ${
                isActive ? "text-ink font-medium" : "text-stone hover:text-ink"
              }`}
            >
              {isActive && (
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 h-4 w-[3px] bg-oxblood rounded-sm"
                  aria-hidden="true"
                />
              )}
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-6 border-t border-line">
        <button
          onClick={logout}
          className="text-xs text-stone hover:text-oxblood transition-colors"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}
