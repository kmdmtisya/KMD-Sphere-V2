// Runs the production build the way the container will (P14-T21): the standalone server, with the
// static assets copied beside it. Usage: `npm run build && npm run start:standalone -- --port 3100`.
import { spawn } from "node:child_process";
import { cpSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const here = (p) => fileURLToPath(new URL(p, import.meta.url));
const standalone = here("../.next/standalone/");
if (!existsSync(`${standalone}server.js`)) {
  console.error("No standalone build found: run `npm run build` first.");
  process.exit(1);
}
cpSync(here("../.next/static"), `${standalone}.next/static`, { recursive: true });
if (existsSync(here("../public"))) cpSync(here("../public"), `${standalone}public`, { recursive: true });

const args = process.argv.slice(2);
const flag = (name, fallback) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : fallback;
};
const env = { ...process.env, PORT: flag("--port", "3000"), HOSTNAME: flag("--hostname", "127.0.0.1") };
const server = spawn(process.execPath, [`${standalone}server.js`], { env, stdio: "inherit" });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.kill(signal));
server.on("exit", (code) => process.exit(code ?? 0));
