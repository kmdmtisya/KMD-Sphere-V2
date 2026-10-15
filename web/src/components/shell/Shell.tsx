"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useStored } from "@/lib/client/local-storage";
import type { NavGroup } from "@/lib/nav/nav";

import { IconButton } from "../controls/controls";
import { CommandPalette } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { useBreakpoint } from "./useBreakpoint";

/**
 * The application shell (P14-T06, WEB_UI_UX_SPECIFICATION.md §3 and §4): skip link, top bar, sidebar,
 * main workspace and the optional right panel.
 *
 * - wide (≥ 1280 px): the sidebar is inline, expanded or collapsed to icons (remembered); the panel docks.
 * - medium (768–1279 px): the sidebar is collapsed to icons and expands as an overlay; the panel is an overlay sheet.
 * - narrow (< 768 px): the sidebar is a drawer behind a menu button; the panel is full width.
 * Esc closes an overlay or the panel; Ctrl/⌘+J toggles the panel. Per-browser conveniences (collapsed
 * state, panel width) are kept in localStorage and never hold account data.
 */
const COLLAPSED_KEY = "ws.sidebar.collapsed";
const PANEL_KEY = "ws.panel.width";
const PANEL_MIN = 320;
const PANEL_MAX = 560;

export function Shell({ groups, user, children }: { groups: NavGroup[]; user: { name: string; email?: string }; children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true } } }));
  const breakpoint = useBreakpoint();
  const pathname = usePathname();
  const [collapsedValue, setCollapsedValue] = useStored(COLLAPSED_KEY);
  const collapsed = collapsedValue === "1";
  const [widthValue, setWidthValue] = useStored(PANEL_KEY);
  const panelWidth = Math.min(PANEL_MAX, Math.max(PANEL_MIN, Number.parseInt(widthValue ?? "", 10) || 380));
  // The overlay belongs to the page and size it was opened on: moving on closes it without an effect.
  const [overlayKey, setOverlayKey] = useState<string | null>(null);
  const here = `${pathname}|${breakpoint}`;
  const overlay = overlayKey === here;
  const setOverlay = (open: boolean | ((v: boolean) => boolean)) => setOverlayKey((open instanceof Function ? open(overlay) : open) ? here : null);
  const [panel, setPanel] = useState(false);
  const [palette, setPalette] = useState(false);
  const menuRef = useRef<HTMLElement | null>(null);


  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOverlayKey(null);
        setPanel(false);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setPanel((v) => !v);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette(true);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const wide = breakpoint === "wide";
  const narrow = breakpoint === "narrow";
  const showMenu = !wide;
  const inlineCollapsed = wide ? collapsed : !narrow;
  const overlayOpen = overlay && !wide;

  function resize(next: number) {
    setWidthValue(String(Math.min(PANEL_MAX, Math.max(PANEL_MIN, next))));
  }

  return (
    <QueryClientProvider client={queryClient}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-2 focus:top-2 focus:z-[60] focus:rounded-[var(--ws-radius-control)] focus:bg-primary focus:px-4 focus:py-2 focus:text-on-primary">
        Skip to the main content
      </a>
      <div className="flex min-h-dvh flex-col bg-scaffold text-fg">
        <TopBar user={user} showMenu={showMenu} onMenu={() => setOverlay((v) => !v)} onPanel={() => setPanel((v) => !v)} onSearch={() => setPalette(true)} panelOpen={panel} />
        <CommandPalette open={palette} onClose={() => setPalette(false)} groups={groups} />
        <div className="relative flex min-h-0 flex-1">
          {!narrow ? (
            <div className={`shrink-0 border-e border-divider bg-surface ${inlineCollapsed ? "w-16" : "w-60"}`}>
              <Sidebar groups={groups} collapsed={inlineCollapsed} />
              {wide ? (
                <div className="p-2">
                  <IconButton icon="sort" label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"} aria-pressed={collapsed} onClick={() => setCollapsedValue(collapsed ? "0" : "1")} />
                </div>
              ) : null}
            </div>
          ) : null}

          {overlayOpen ? (
            <>
              <div aria-hidden="true" className="fixed inset-0 z-30 bg-fg/40" onClick={() => setOverlay(false)} />
              <div role="dialog" aria-label="Menu" ref={(el) => { menuRef.current = el; }} className="fixed inset-y-0 start-0 z-40 w-64 overflow-y-auto border-e border-divider bg-surface pt-12">
                <div className="absolute end-2 top-2">
                  <IconButton icon="expand" label="Close the menu" onClick={() => setOverlay(false)} />
                </div>
                <Sidebar groups={groups} collapsed={false} onNavigate={() => setOverlay(false)} />
              </div>
            </>
          ) : null}

          <main id="main" tabIndex={-1} className="min-w-0 flex-1 p-4 md:p-6">
            {children}
          </main>

          {panel ? (
            <aside
              aria-label="Copilot"
              style={wide ? { width: panelWidth } : undefined}
              className={`shrink-0 border-s border-divider bg-surface p-4 ${wide ? "relative" : "fixed inset-y-0 end-0 z-40 w-full max-w-[560px] shadow-lg"}`}
            >
              {wide ? (
                <div
                  role="separator"
                  aria-orientation="vertical"
                  aria-label="Resize the Copilot panel"
                  aria-valuemin={PANEL_MIN}
                  aria-valuemax={PANEL_MAX}
                  aria-valuenow={panelWidth}
                  tabIndex={0}
                  className="absolute inset-y-0 -start-1 w-2 cursor-col-resize hover:bg-primary/30 focus-visible:bg-primary/40"
                  onKeyDown={(e) => {
                    if (e.key === "ArrowLeft") resize(panelWidth + 20);
                    if (e.key === "ArrowRight") resize(panelWidth - 20);
                  }}
                  onPointerDown={(e) => {
                    const startX = e.clientX;
                    const start = panelWidth;
                    const move = (m: PointerEvent) => resize(start + (startX - m.clientX));
                    const up = () => {
                      window.removeEventListener("pointermove", move);
                      window.removeEventListener("pointerup", up);
                    };
                    window.addEventListener("pointermove", move);
                    window.addEventListener("pointerup", up);
                  }}
                />
              ) : null}
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-semibold">Copilot</h2>
                <IconButton icon="expand" label="Close the Copilot panel" onClick={() => setPanel(false)} />
              </div>
              <p className="mt-3 text-fg-muted">
                The Copilot, scoped to the page you are on, arrives with P14-T12. It will explain your own figures, separate facts from assumptions, and never give personal investment advice or place trades.
              </p>
            </aside>
          ) : null}
        </div>
      </div>
    </QueryClientProvider>
  );
}
