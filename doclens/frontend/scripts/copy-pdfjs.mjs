// Serve the pdf.js worker and cMaps (needed for Japanese PDFs) from /public, matching the installed version.
import { copyFileSync, cpSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const pdfjs = dirname(require.resolve("pdfjs-dist/package.json"));
mkdirSync("public", { recursive: true });
copyFileSync(join(pdfjs, "build", "pdf.worker.min.mjs"), "public/pdf.worker.min.mjs");
cpSync(join(pdfjs, "cmaps"), "public/cmaps", { recursive: true });
