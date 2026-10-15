// CSS counterpart of wealthsphere/no-colour-literals: colour literals may appear only in the
// generated token files (src/tokens). Exits 1 and lists every offending line.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { findColour } from "../eslint-rules/no-colour-literals.mjs";

const root = new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const allowed = join(root, "src", "tokens") + sep;

function* cssFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* cssFiles(path);
    else if (name.endsWith(".css")) yield path;
  }
}

const problems = [];
for (const file of cssFiles(join(root, "src"))) {
  if (file.startsWith(allowed)) continue;
  readFileSync(file, "utf8").split(/\r?\n/).forEach((line, i) => {
    const colour = findColour(line.replace(/\/\*.*?\*\//g, ""));
    if (colour) problems.push(`${relative(root, file)}:${i + 1}: colour literal '${colour}'`);
  });
}
if (problems.length) {
  console.error(problems.join("\n"));
  console.error("Use design tokens (CSS variables from src/tokens) instead of colour literals.");
  process.exit(1);
}
console.log("CSS colour check: no colour literals outside src/tokens");
