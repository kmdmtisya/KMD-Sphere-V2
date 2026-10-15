import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AppearanceSelector, ThemeCycleButton } from "@/components/theme/appearance";

import { FollowingPanel, GalleryPanel } from "./Gallery";

export const metadata: Metadata = { title: "Component gallery · WealthSphere", robots: { index: false } };

/**
 * The web design system gallery (P14-T03, `/_gallery`): every component in the light and dark
 * themes side by side, with DEMO data. Available in development, and in a production build only when
 * it was built with WS_ENABLE_GALLERY=1 (the visual tests); deployed builds never include it.
 */
export default function GalleryPage() {
  if (process.env.NODE_ENV === "production" && process.env.WS_ENABLE_GALLERY !== "1") notFound();
  return (
    <main className="min-h-dvh bg-scaffold">
      <h1 className="sr-only">WealthSphere component gallery</h1>
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-divider bg-surface p-6 text-fg">
        <AppearanceSelector />
        <ThemeCycleButton />
      </div>
      <FollowingPanel />
      <div className="grid 2xl:grid-cols-2">
        <GalleryPanel theme="light" />
        <GalleryPanel theme="dark" />
      </div>
    </main>
  );
}
