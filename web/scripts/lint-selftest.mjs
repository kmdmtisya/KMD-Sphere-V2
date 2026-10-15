// Proves the WealthSphere lint guards fire (P14-T04 acceptance: "the money-arithmetic rule fails
// on a seeded violation"). Lints the seeded fixtures with the project config and fails unless each
// guard reports the expected violations.
import { ESLint } from "eslint";

import wealthsphere from "../eslint-rules/index.mjs";

const expectations = [
  { file: "lint-fixtures/money-violation.ts", rule: "wealthsphere/no-money-arithmetic", atLeast: 3 },
  { file: "lint-fixtures/colour-violation.tsx", rule: "wealthsphere/no-colour-literals", atLeast: 3 },
];

const eslint = new ESLint({
  ignore: false,
  overrideConfig: {
    files: ["lint-fixtures/**"],
    plugins: { wealthsphere },
    rules: {
      "wealthsphere/no-money-arithmetic": "error",
      "wealthsphere/no-colour-literals": "error",
    },
  },
});

let failed = false;
for (const { file, rule, atLeast } of expectations) {
  const [result] = await eslint.lintFiles([file]);
  const hits = result.messages.filter((m) => m.ruleId === rule).length;
  const ok = hits >= atLeast;
  failed ||= !ok;
  console.log(`${ok ? "ok  " : "FAIL"} ${rule}: ${hits} violation(s) in ${file} (expected at least ${atLeast})`);
}
if (failed) {
  console.error("A lint guard did not fire on its seeded violation.");
  process.exit(1);
}
