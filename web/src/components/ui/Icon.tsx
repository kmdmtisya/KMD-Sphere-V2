/**
 * Inline stroke icons drawn with `currentColor`, so they follow the text colour of the active theme.
 * Decorative by default (`aria-hidden`); pass `label` when the icon is the only content.
 */
const PATHS = {
  arrowUp: "M12 19V5M5 12l7-7 7 7",
  arrowDown: "M12 5v14M5 12l7 7 7-7",
  minus: "M5 12h14",
  info: "M12 16v-4M12 8h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  refresh: "M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6",
  expand: "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
  table: "M3 5h18v14H3zM3 10h18M3 15h18M9 5v14",
  chart: "M3 3v18h18M7 15l4-4 3 3 5-6",
  clock: "M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0z",
  inbox: "M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z",
  shield: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  sort: "M7 4v16M3 8l4-4 4 4M17 20V4M13 16l4 4 4-4",
  sun: "M12 3v2M12 19v2M5 12H3M21 12h-2M6.3 6.3 4.9 4.9M19.1 19.1l-1.4-1.4M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0z",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  monitor: "M3 4h18v12H3zM8 20h8M12 16v4",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16, label, className }: { name: IconName; size?: number; label?: string; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
