/**
 * wealthsphere/no-colour-literals (P14-T04; mirrors the Flutter style guard).
 *
 * Colours come only from the generated design tokens (CSS variables), so every surface follows
 * Light, Dark and System (docs/web/WEB_THEME_SYSTEM.md). This rule reports colour literals in
 * string and template literals, including Tailwind arbitrary values such as `bg-[#0B1B2B]`:
 * hex colours (#rgb, #rgba, #rrggbb, #rrggbbaa) and rgb(), rgba(), hsl(), hsla(), hwb(), lab(),
 * lch(), oklab(), oklch() and color() functions. CSS files are checked by
 * `scripts/check-css-colours.mjs`. The generated token files are the only exception (configured in
 * eslint.config.mjs).
 */

const HEX = /(^|[^&\w])#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-zA-Z_-])/;
const FUNCTIONS = /\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/i;

export function findColour(text) {
  const hex = HEX.exec(text);
  if (hex) return text.slice(hex.index + hex[1].length).match(/^#[0-9a-fA-F]+/)[0];
  const fn = FUNCTIONS.exec(text);
  return fn ? fn[0] : null;
}

/** @type {import("eslint").Rule.RuleModule} */
const rule = {
  meta: {
    type: "problem",
    docs: { description: "Forbid colour literals outside the generated design tokens" },
    schema: [],
    messages: {
      literal:
        "Colour literal '{{colour}}': use a design token (CSS variable or Tailwind token class) so the light, dark and system themes apply.",
    },
  },
  create(context) {
    function check(node, text) {
      const colour = findColour(text);
      if (colour) context.report({ node, messageId: "literal", data: { colour } });
    }
    return {
      Literal(node) {
        if (typeof node.value === "string") check(node, node.value);
      },
      TemplateElement(node) {
        check(node, node.value.cooked ?? node.value.raw);
      },
    };
  },
};

export default rule;
