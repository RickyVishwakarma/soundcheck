// Copy the single-file build into the Python package, so `soundcheck html`
// works from a plain pip install with no Node toolchain.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "dist", "index.html");
const dest = join(here, "..", "..", "soundcheck", "assets", "report_template.html");

mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log(`synced ${src} -> ${dest}`);
