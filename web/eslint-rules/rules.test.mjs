import { RuleTester } from "eslint";
import { describe, expect, it } from "vitest";

import noColourLiterals, { findColour } from "./no-colour-literals.mjs";
import noMoneyArithmetic, { isMoneyName } from "./no-money-arithmetic.mjs";

RuleTester.describe = describe;
RuleTester.it = it;
const tester = new RuleTester({ languageOptions: { ecmaVersion: 2024, sourceType: "module" } });

describe("isMoneyName", () => {
  it("splits camelCase and snake_case words", () => {
    for (const name of ["amount", "marketValue", "total_value", "fxRate", "values", "PNLPercent", "unitsHeld", "netWorth"]) {
      expect(isMoneyName(name), name).toBe(true);
    }
    for (const name of ["generateId", "iterate", "index", "count", "width", "separator", "evaluation"]) {
      expect(isMoneyName(name), name).toBe(false);
    }
  });
});

tester.run("no-money-arithmetic", noMoneyArithmetic, {
  valid: [
    "const next = index + 1;",
    "const label = `${row.amount} ${row.currency}`;",
    "new Intl.NumberFormat('en', { style: 'currency', currency: 'USD' }).format(row.amount);",
    "const width = columns.length * 120;",
    "const id = generateId() + 1;",
  ],
  invalid: [
    { code: "const pnl = row.market_value - row.cost_basis;", errors: [{ messageId: "arithmetic" }] },
    { code: "const sum = totalAmount + fee;", errors: [{ messageId: "arithmetic" }] },
    { code: "balance += deposit;", errors: [{ messageId: "arithmetic" }] },
    { code: "const x = Number(row.amount);", errors: [{ messageId: "conversion" }] },
    { code: "const x = parseFloat(price);", errors: [{ messageId: "conversion" }] },
    { code: "const x = +holding.marketValue;", errors: [{ messageId: "conversion" }] },
    { code: "const x = Math.round(fxRate);", errors: [{ messageId: "conversion" }] },
    { code: "const pct = gain / row.totalValue;", errors: [{ messageId: "arithmetic" }] },
  ],
});

describe("findColour", () => {
  it("finds hex and colour functions, not other hashes", () => {
    expect(findColour("#0B1B2B")).toBe("#0B1B2B");
    expect(findColour("bg-[#102A43] p-2")).toBe("#102A43");
    expect(findColour("rgb(16, 42, 67)")).toBe("rgb(");
    expect(findColour("oklch(0.5 0.1 200)")).toBe("oklch(");
    expect(findColour("#portfolio")).toBeNull();
    expect(findColour("&#1234;")).toBeNull();
    expect(findColour("bg-surface text-fg")).toBeNull();
    expect(findColour("var(--ws-accent)")).toBeNull();
  });
});

tester.run("no-colour-literals", noColourLiterals, {
  valid: ["const c = 'var(--ws-surface)';", "const cls = 'bg-surface text-fg';", "const s = 'Ticket #12';"],
  invalid: [
    { code: "const c = '#fff';", errors: [{ messageId: "literal" }] },
    { code: "const cls = `bg-[#102A43] ${x}`;", errors: [{ messageId: "literal" }] },
    { code: "const c = 'hsl(200 50% 50%)';", errors: [{ messageId: "literal" }] },
  ],
});
