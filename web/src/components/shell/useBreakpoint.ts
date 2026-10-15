"use client";

import { useSyncExternalStore } from "react";

/** wide ≥ 1280 px, medium 768–1279 px, narrow < 768 px (WEB_UI_UX_SPECIFICATION.md §4). */
export type Breakpoint = "wide" | "medium" | "narrow";

function subscribe(onChange: () => void): () => void {
  const queries = [window.matchMedia("(min-width: 1280px)"), window.matchMedia("(min-width: 768px)")];
  for (const q of queries) q.addEventListener("change", onChange);
  return () => queries.forEach((q) => q.removeEventListener("change", onChange));
}

function snapshot(): Breakpoint {
  if (window.matchMedia("(min-width: 1280px)").matches) return "wide";
  return window.matchMedia("(min-width: 768px)").matches ? "medium" : "narrow";
}

export function useBreakpoint(): Breakpoint {
  return useSyncExternalStore(subscribe, snapshot, () => "wide");
}
