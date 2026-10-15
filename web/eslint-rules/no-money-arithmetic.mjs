/**
 * wealthsphere/no-money-arithmetic (P14-T04, QG-26.3).
 *
 * The backend is authoritative for every financial figure (ADR-0003, ADR-0018). The web shows the
 * decimal strings the API sends and never calculates money. This rule reports, for any value whose
 * name looks like money:
 *   - arithmetic: `a + b`, `a - b`, `a * b`, `a / b`, `a % b`, `a ** b` and the compound
 *     assignments `+=`, `-=`, `*=`, `/=`, `%=`, `**=`;
 *   - conversion to a binary float: `Number(x)`, `parseFloat(x)`, `parseInt(x)`, unary `+x`,
 *     `Math.round(x)` and the other `Math.*` functions.
 * A name looks like money when one of its words (split at camelCase and snake_case boundaries,
 * plural "s" ignored) is in MONEY_WORDS: `amount`, `marketValue`, `row.total_value`, `fxRate` and
 * `values` do; `generateId`, `iterate` and `index` do not.
 *
 * Formatting a decimal string for display (Intl.NumberFormat with a string, or the shared
 * formatter) is not arithmetic and is allowed.
 */

const MONEY_WORDS = [
  "amount",
  "balance",
  "price",
  "value",
  "total",
  "cost",
  "fee",
  "pnl",
  "profit",
  "loss",
  "income",
  "wealth",
  "worth",
  "subtotal",
  "principal",
  "contribution",
  "equity",
  "margin",
  "notional",
  "quantity",
  "qty",
  "units",
  "rate",
];

const MONEY = new Set(MONEY_WORDS);

/** Splits `marketValue`, `total_value` or `PNLPercent` into lower-case words. */
function wordsOf(name) {
  return name
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .split(/[^A-Za-z0-9]+/)
    .filter(Boolean)
    .map((w) => w.toLowerCase());
}

function isMoneyName(name) {
  return wordsOf(name).some((w) => MONEY.has(w) || (w.endsWith("s") && MONEY.has(w.slice(0, -1))));
}
const ARITHMETIC = new Set(["+", "-", "*", "/", "%", "**"]);
const COMPOUND = new Set(["+=", "-=", "*=", "/=", "%=", "**="]);
const FLOAT_CALLS = new Set(["Number", "parseFloat", "parseInt"]);

/** The name a value is known by: an identifier, or the last property of a member expression. */
function nameOf(node) {
  if (!node) return null;
  switch (node.type) {
    case "Identifier":
      return node.name;
    case "MemberExpression":
      if (!node.computed && node.property.type === "Identifier") return node.property.name;
      if (node.computed && node.property.type === "Literal" && typeof node.property.value === "string") {
        return node.property.value;
      }
      return null;
    case "ChainExpression":
      return nameOf(node.expression);
    case "TSNonNullExpression":
    case "TSAsExpression":
    case "TSSatisfiesExpression":
      return nameOf(node.expression);
    default:
      return null;
  }
}

function looksLikeMoney(node) {
  const name = nameOf(node);
  return name !== null && isMoneyName(name);
}

function isMathCall(callee) {
  return (
    callee.type === "MemberExpression" &&
    !callee.computed &&
    callee.object.type === "Identifier" &&
    callee.object.name === "Math"
  );
}

/** @type {import("eslint").Rule.RuleModule} */
const rule = {
  meta: {
    type: "problem",
    docs: {
      description:
        "Forbid arithmetic on, or binary-float conversion of, money values in the web client; the backend is authoritative",
    },
    schema: [],
    messages: {
      arithmetic:
        "'{{name}}' looks like money: the web must not calculate with it ({{operator}}). Show the value the API sends (ADR-0003, QG-26.3).",
      conversion:
        "'{{name}}' looks like money: do not convert it to a binary float ({{call}}). Format the decimal string for display instead (ADR-0003, QG-26.3).",
    },
  },
  create(context) {
    function reportArithmetic(node, operand, operator) {
      context.report({ node, messageId: "arithmetic", data: { name: nameOf(operand), operator } });
    }
    return {
      BinaryExpression(node) {
        if (!ARITHMETIC.has(node.operator)) return;
        if (looksLikeMoney(node.left)) reportArithmetic(node, node.left, node.operator);
        else if (looksLikeMoney(node.right)) reportArithmetic(node, node.right, node.operator);
      },
      AssignmentExpression(node) {
        if (!COMPOUND.has(node.operator)) return;
        if (looksLikeMoney(node.left)) reportArithmetic(node, node.left, node.operator);
        else if (looksLikeMoney(node.right)) reportArithmetic(node, node.right, node.operator);
      },
      UnaryExpression(node) {
        if (node.operator === "+" && looksLikeMoney(node.argument)) {
          context.report({ node, messageId: "conversion", data: { name: nameOf(node.argument), call: "unary +" } });
        }
      },
      CallExpression(node) {
        const arg = node.arguments.find((a) => looksLikeMoney(a));
        if (!arg) return;
        const { callee } = node;
        if (callee.type === "Identifier" && FLOAT_CALLS.has(callee.name)) {
          context.report({ node, messageId: "conversion", data: { name: nameOf(arg), call: `${callee.name}()` } });
        } else if (isMathCall(callee)) {
          context.report({
            node,
            messageId: "conversion",
            data: { name: nameOf(arg), call: `Math.${callee.property.name}()` },
          });
        }
      },
    };
  },
};

export default rule;
export { MONEY_WORDS, isMoneyName };
