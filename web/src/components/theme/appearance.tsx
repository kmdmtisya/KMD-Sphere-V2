"use client";

import { useId, useState, useSyncExternalStore } from "react";

import {
  nextPreference,
  parsePreference,
  PREFERENCE_LABELS,
  resolveTheme,
  THEME_CHANNEL,
  themeCookie,
  type ThemePreference,
} from "@/lib/theme/theme";

import { Icon, type IconName } from "../ui/Icon";

/**
 * Appearance (P14-T25, docs/web/WEB_THEME_SYSTEM.md §5 and §7). The source of truth on this page is
 * `<html data-theme-pref>`, set before the first paint by the boot script. A change applies in the
 * same frame, is kept in the cookie, reaches other open tabs, and is saved to the account
 * (/me/preferences) when signed in. A change of the device's setting moves only the resolved theme;
 * the saved choice stays "system".
 */
const ICONS: Record<ThemePreference, IconName> = { light: "sun", dark: "moon", system: "monitor" };
const DEVICE_DARK = "(prefers-color-scheme: dark)";

function readPreference(): ThemePreference {
  return parsePreference(document.documentElement.getAttribute("data-theme-pref"));
}

function subscribePreference(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme-pref"] });
  let channel: BroadcastChannel | null = null;
  try {
    channel = new BroadcastChannel(THEME_CHANNEL);
    // Another tab changed the appearance: apply it here too (it saved to the account already).
    channel.onmessage = (event: MessageEvent) => applyLocally(parsePreference(String(event.data)));
  } catch {
    channel = null;
  }
  return () => {
    observer.disconnect();
    channel?.close();
  };
}

function subscribeDevice(onChange: () => void): () => void {
  const media = window.matchMedia(DEVICE_DARK);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

function applyLocally(preference: ThemePreference): void {
  document.documentElement.setAttribute("data-theme-pref", preference);
  document.cookie = themeCookie(preference);
}

type SaveResult = "saved" | "local" | "failed";

/** Saves to the account when signed in (the CSRF cookie exists only then); never blocks the change. */
async function saveToAccount(preference: ThemePreference): Promise<SaveResult> {
  const csrf = /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1];
  if (!csrf) return "local";
  try {
    const response = await fetch("/api/proxy/me/preferences", {
      method: "PATCH",
      headers: { "content-type": "application/json", "x-csrf-token": decodeURIComponent(csrf) },
      body: JSON.stringify({ theme_mode: preference }),
    });
    if (response.ok) return "saved";
    return response.status === 401 ? "local" : "failed";
  } catch {
    return "failed";
  }
}

/** Applies a choice everywhere: this page now, other tabs, this browser and the account. */
export async function choosePreference(preference: ThemePreference): Promise<SaveResult> {
  applyLocally(preference);
  try {
    const channel = new BroadcastChannel(THEME_CHANNEL);
    channel.postMessage(preference);
    channel.close();
  } catch {
    // Tabs update on their next load.
  }
  return saveToAccount(preference);
}

export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribePreference, readPreference, () => "system");
}

export function useDeviceDark(): boolean {
  return useSyncExternalStore(subscribeDevice, () => window.matchMedia(DEVICE_DARK).matches, () => false);
}

const NOT_SAVED = "Saved on this browser only. Your account could not be updated; try again later.";

/** Settings › Appearance and the profile menu: a radio group with Light, Dark and System. */
export function AppearanceSelector() {
  const preference = useThemePreference();
  const deviceDark = useDeviceDark();
  const [notice, setNotice] = useState<string | null>(null);
  const name = useId();
  const systemHint = `${name}-system`;

  async function choose(value: ThemePreference) {
    setNotice(null);
    if ((await choosePreference(value)) === "failed") setNotice(NOT_SAVED);
  }

  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-[length:var(--ws-font-size-label)] font-semibold">Appearance</legend>
      <div className="flex flex-wrap gap-2">
        {(["light", "dark", "system"] as const).map((value) => (
          <label
            key={value}
            className="inline-flex min-h-9 cursor-pointer items-center gap-2 rounded-[var(--ws-radius-control)] border border-line px-3 text-[length:var(--ws-font-size-label)] font-semibold text-fg has-checked:border-primary has-checked:bg-primary has-checked:text-on-primary has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus"
          >
            <input
              type="radio"
              name={name}
              value={value}
              checked={preference === value}
              onChange={() => void choose(value)}
              aria-describedby={value === "system" ? systemHint : undefined}
              className="sr-only"
            />
            <Icon name={ICONS[value]} size={16} />
            {PREFERENCE_LABELS[value]}
          </label>
        ))}
      </div>
      <p id={systemHint} className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        System follows your device (currently {deviceDark ? "Dark" : "Light"}).
      </p>
      <p role="status" className="text-[length:var(--ws-font-size-caption)] text-warning-text">
        {notice}
      </p>
    </fieldset>
  );
}

/** The compact top-bar control: cycles Light → Dark → System, and says so. */
export function ThemeCycleButton() {
  const preference = useThemePreference();
  const deviceDark = useDeviceDark();
  const next = nextPreference(preference);
  const shown = preference === "system" ? ` (${PREFERENCE_LABELS[resolveTheme(preference, deviceDark)]})` : "";
  const label = `Appearance: ${PREFERENCE_LABELS[preference]}${shown}. Switch to ${PREFERENCE_LABELS[next]}`;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={() => void choosePreference(next)}
      className="inline-flex size-9 items-center justify-center rounded-[var(--ws-radius-control)] border border-divider text-fg-muted hover:bg-divider/60 hover:text-fg"
    >
      <Icon name={ICONS[preference]} size={16} />
    </button>
  );
}
