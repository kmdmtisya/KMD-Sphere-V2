/**
 * Display helpers for the decimal strings the API sends (ADR-0003, ADR-0006). Nothing here does
 * arithmetic: values are formatted by Intl.NumberFormat from the string itself (exact for decimal
 * strings), and compared as strings. The backend remains the only place money is calculated.
 */

const DECIMAL = /^-?\d+(\.\d+)?$/;

/** True for a plain decimal string such as "1234.50" or "-0.07". */
export function isDecimalString(value: string): boolean {
  return DECIMAL.test(value);
}

export type Sign = "positive" | "negative" | "zero";

/** The sign of a decimal string, read from its characters (no conversion to a number). */
export function signOf(value: string): Sign {
  if (!isDecimalString(value)) throw new Error(`not a decimal string: ${value}`);
  const digits = value.replace("-", "").replace(".", "");
  if (/^0+$/.test(digits)) return "zero";
  return value.startsWith("-") ? "negative" : "positive";
}

/** The absolute value of a decimal string, as a string (drops a leading minus sign). */
export function absoluteOf(value: string): string {
  return value.startsWith("-") ? value.slice(1) : value;
}

function normalise(value: string): { negative: boolean; whole: string; fraction: string } {
  const negative = signOf(value) === "negative";
  const [whole, fraction = ""] = absoluteOf(value).split(".");
  return { negative, whole: whole.replace(/^0+(?=\d)/, ""), fraction: fraction.replace(/0+$/, "") };
}

function compareMagnitude(a: { whole: string; fraction: string }, b: { whole: string; fraction: string }): number {
  if (a.whole.length !== b.whole.length) return a.whole.length < b.whole.length ? -1 : 1;
  if (a.whole !== b.whole) return a.whole < b.whole ? -1 : 1;
  const width = Math.max(a.fraction.length, b.fraction.length);
  const fa = a.fraction.padEnd(width, "0");
  const fb = b.fraction.padEnd(width, "0");
  return fa === fb ? 0 : fa < fb ? -1 : 1;
}

/**
 * Orders two decimal strings exactly, for sorting tables (-1, 0 or 1). Digit strings of equal
 * length compare like numbers, so no conversion to a binary float is needed.
 */
export function compareDecimalStrings(a: string, b: string): number {
  const x = normalise(a);
  const y = normalise(b);
  if (x.negative !== y.negative) return x.negative ? -1 : 1;
  const magnitude = compareMagnitude(x, y);
  return x.negative ? -magnitude : magnitude;
}

export type MoneyParts = {
  /** The full formatted text, for screen readers and copy. */
  text: string;
  /** The major part, for example "$325,980". */
  major: string;
  /** The minor part including the decimal separator, for example ".65" (may be empty). */
  minor: string;
};

/**
 * Formats a decimal string as money in its currency. The minor part is returned separately so
 * cards can show it in the muted style of the reference design (WEB_DESIGN_REFERENCE_ANALYSIS.md).
 */
export function formatMoney(value: string, currency: string, locale = "en"): MoneyParts {
  if (!isDecimalString(value)) throw new Error(`not a decimal string: ${value}`);
  const format = new Intl.NumberFormat(locale, { style: "currency", currency });
  // Intl.NumberFormat formats a decimal string exactly (no binary rounding).
  const parts = format.formatToParts(value as unknown as number);
  const split = parts.findIndex((p) => p.type === "decimal");
  const join = (list: Intl.NumberFormatPart[]) => list.map((p) => p.value).join("");
  if (split < 0) return { text: join(parts), major: join(parts), minor: "" };
  const fractionEnd = parts.findIndex((p, i) => i > split && p.type !== "fraction");
  const minorParts = fractionEnd < 0 ? parts.slice(split) : parts.slice(split, fractionEnd);
  const rest = fractionEnd < 0 ? [] : parts.slice(fractionEnd);
  return { text: join(parts), major: join(parts.slice(0, split)) + join(rest), minor: join(minorParts) };
}

/** Formats a decimal string as a percentage figure ("14.09" is shown as "14.09%"). */
export function formatPercent(value: string, locale = "en", fractionDigits = 2): string {
  if (!isDecimalString(value)) throw new Error(`not a decimal string: ${value}`);
  const format = new Intl.NumberFormat(locale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
  return `${format.format(value as unknown as number)}%`;
}
