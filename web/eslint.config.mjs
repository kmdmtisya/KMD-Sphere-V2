import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

import wealthsphere from "./eslint-rules/index.mjs";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // WealthSphere guards (P14-T04): the backend is authoritative for money (QG-26.3), and colours
    // come only from the generated design tokens.
    files: ["src/**/*.{ts,tsx,js,jsx,mjs}"],
    plugins: { wealthsphere },
    rules: {
      "wealthsphere/no-money-arithmetic": "error",
      "wealthsphere/no-colour-literals": "error",
    },
  },
  {
    // Generated token files are the one place colour values may appear.
    files: ["src/tokens/**"],
    rules: { "wealthsphere/no-colour-literals": "off" },
  },
  {
    // The single, documented conversion of decimal strings to numbers for chart geometry only;
    // nothing is calculated from them (see the file's header).
    files: ["src/lib/chart/plot-values.ts"],
    rules: { "wealthsphere/no-money-arithmetic": "off" },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "src/lib/api/schema.d.ts",
    // Seeded violations for `npm run lint:selftest`; linting them normally would always fail.
    "lint-fixtures/**",
    "playwright-report/**",
    "test-results/**",
  ]),
]);

export default eslintConfig;
