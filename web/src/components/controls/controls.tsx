"use client";

import { useId } from "react";

import { Icon, type IconName } from "../ui/Icon";

/** Buttons and the segmented control. Targets are at least 36 px high (WCAG 2.5.8 needs 24). */

const VARIANT = {
  primary: "bg-primary text-on-primary hover:brightness-110",
  secondary: "border border-line bg-surface text-fg hover:bg-surface-elevated",
  ghost: "text-fg hover:bg-divider/60",
};

export function Button({
  variant = "secondary",
  icon,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof VARIANT; icon?: IconName }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex min-h-9 items-center justify-center gap-2 rounded-[var(--ws-radius-control)] px-4 text-[length:var(--ws-font-size-label)] font-semibold transition-[filter,background-color] duration-[var(--ws-motion-fast)] disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${props.className ?? ""}`}
    >
      {icon ? <Icon name={icon} size={16} /> : null}
      {children}
    </button>
  );
}

/** A square icon-only button; the label is required and becomes its accessible name and tooltip. */
export function IconButton({ icon, label, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconName; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      {...props}
      className={`inline-flex size-9 items-center justify-center rounded-[var(--ws-radius-control)] border border-divider text-fg-muted hover:bg-divider/60 hover:text-fg ${props.className ?? ""}`}
    >
      <Icon name={icon} size={16} />
    </button>
  );
}

/**
 * A single choice among a few options (period ranges, chart type), as a radio group: arrow keys
 * move between options, the choice applies at once (mirrors the mobile `PeriodSelector`).
 */
export function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  const name = useId();
  return (
    <fieldset className="inline-flex rounded-[var(--ws-radius-control)] border border-line p-0.5">
      <legend className="sr-only">{label}</legend>
      {options.map((o) => (
        <label
          key={o.value}
          className="relative inline-flex min-h-8 cursor-pointer items-center rounded-[calc(var(--ws-radius-control)-2px)] px-3 text-[length:var(--ws-font-size-label)] font-semibold text-fg-muted has-checked:bg-primary has-checked:text-on-primary has-focus-visible:outline-2 has-focus-visible:outline-focus"
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={o.value === value}
            onChange={() => onChange(o.value)}
            className="sr-only"
          />
          {o.label}
        </label>
      ))}
    </fieldset>
  );
}
