/**
 * Appearance: Light, Dark or System (P14-T25, docs/web/WEB_THEME_SYSTEM.md). The choice lives in
 * `theme_mode` of /me/preferences when signed in and in the `__Host-ws_theme` cookie on this browser.
 * The cookie holds only the word; it is readable by scripts because the boot script needs it.
 */
export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_COOKIE = "__Host-ws_theme";
export const THEME_CHANNEL = "ws-theme";
const ONE_YEAR = 60 * 60 * 24 * 365;

/** Any value other than the three words means "system" (corrupt or future values never break). */
export function parsePreference(value: string | null | undefined): ThemePreference {
  return value === "light" || value === "dark" ? value : "system";
}

export function themeCookie(preference: ThemePreference): string {
  return `${THEME_COOKIE}=${preference}; Path=/; Max-Age=${ONE_YEAR}; SameSite=Lax; Secure`;
}

/**
 * Runs in <head> while the HTML is parsed, before the first paint: copies the saved choice from the
 * cookie onto <html data-theme-pref>. The CSS does the rest ("system" follows prefers-color-scheme),
 * so the first painted frame already has the right theme (Next.js guide: preventing flash before
 * hydration; reading cookies in the root layout would make every page dynamic). Without JavaScript the
 * page follows the device (System).
 */
export const THEME_BOOT_SCRIPT = `(function(){try{var m=document.cookie.match(/(?:^|; )${THEME_COOKIE}=(light|dark|system)(?:;|$)/);document.documentElement.setAttribute("data-theme-pref",m?m[1]:"system")}catch(e){}})()`;

/** The theme actually shown for a preference and the device's setting. */
export function resolveTheme(preference: ThemePreference, deviceDark: boolean): ResolvedTheme {
  if (preference === "system") return deviceDark ? "dark" : "light";
  return preference;
}

export const PREFERENCE_LABELS: Record<ThemePreference, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

/** The order of the top-bar cycle button: Light → Dark → System → Light. */
export function nextPreference(preference: ThemePreference): ThemePreference {
  return preference === "light" ? "dark" : preference === "dark" ? "system" : "light";
}
