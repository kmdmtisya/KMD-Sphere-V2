import type { Metadata, Viewport } from "next";

import { THEME_BOOT_SCRIPT } from "@/lib/theme/theme";

import "./globals.css";

export const metadata: Metadata = {
  title: "WealthSphere",
  description: "WealthSphere web portal",
};

/** The browser chrome (address bar) follows the page's scaffold colour in each theme. */
export const viewport: Viewport = {
  colorScheme: "light dark",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // The server renders "system"; the boot script applies the saved appearance before the first
  // paint (src/lib/theme/theme.ts), so the attribute may differ from the server's at hydration.
  return (
    <html lang="en" data-theme-pref="system" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
