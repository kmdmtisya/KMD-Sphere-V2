"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { activeItem, type NavGroup } from "@/lib/nav/nav";

import { Icon } from "../ui/Icon";

/**
 * The sidebar (P14-T06): groups map onto the mobile tabs. The active page is marked by a bar and
 * `aria-current`, not by colour alone. Collapsed, it shows icons with accessible names.
 */
export function Sidebar({ groups, collapsed, onNavigate }: { groups: NavGroup[]; collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = activeItem(pathname, groups.flatMap((g) => g.items));
  return (
    <nav aria-label="Main" className="flex h-full flex-col gap-4 overflow-y-auto p-2">
      {groups.map((group) => (
        <div key={group.id}>
          <p className={`px-3 pb-1 text-[length:var(--ws-font-size-caption)] font-semibold uppercase tracking-wide text-fg-muted ${collapsed ? "sr-only" : ""}`}>
            {group.label}
          </p>
          <ul className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const current = active?.href === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={current ? "page" : undefined}
                    title={collapsed ? item.label : undefined}
                    onClick={onNavigate}
                    className={`relative flex min-h-9 items-center gap-3 rounded-[var(--ws-radius-control)] px-3 font-medium hover:bg-divider/60 ${
                      current ? "bg-surface-elevated text-fg" : "text-fg-muted"
                    } ${collapsed ? "justify-center" : ""}`}
                  >
                    {current ? <span aria-hidden="true" className="absolute inset-y-1.5 start-0 w-1 rounded-full bg-primary" /> : null}
                    <Icon name={item.icon} size={18} />
                    <span className={collapsed ? "sr-only" : ""}>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
