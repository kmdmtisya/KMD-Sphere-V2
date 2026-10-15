/** Local ESLint plugin with the WealthSphere web guards (P14-T04). */
import noColourLiterals from "./no-colour-literals.mjs";
import noMoneyArithmetic from "./no-money-arithmetic.mjs";

const plugin = {
  meta: { name: "eslint-plugin-wealthsphere" },
  rules: {
    "no-money-arithmetic": noMoneyArithmetic,
    "no-colour-literals": noColourLiterals,
  },
};

export default plugin;
