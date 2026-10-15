import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "WealthSphere",
  description: "WealthSphere web portal",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // "system" until P14-T25 reads the saved appearance (cookie, then /me/preferences).
  return (
    <html lang="en" data-theme-pref="system">
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
