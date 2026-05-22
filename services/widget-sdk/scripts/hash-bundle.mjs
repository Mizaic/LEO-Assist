// Post-build script: produces a content-addressed copy of the widget bundle.
//
// Usage: node scripts/hash-bundle.mjs
//
// Reads  dist/v1/leo-widget.js
// Writes dist/v1/leo-widget.<sha256[0:8]>.js  (immutable CDN artefact)
//        dist/v1/leo-widget.<sha256[0:8]>.js.map (if sourcemap present)
//        dist/v1/.bundle  (the hashed filename, read by workflow + demo build)
//
// The sourceMappingURL comment inside the bundle is rewritten to point at
// the hashed map filename so DevTools resolves it correctly.

import { createHash } from "node:crypto";
import {
  readFileSync,
  writeFileSync,
  copyFileSync,
  existsSync,
} from "node:fs";

const SRC_JS = "dist/v1/leo-widget.js";
const SRC_MAP = `${SRC_JS}.map`;

const content = readFileSync(SRC_JS, "utf8");
const hash = createHash("sha256").update(content).digest("hex").slice(0, 8);
const hashedJs = `leo-widget.${hash}.js`;
const hashedMap = `${hashedJs}.map`;

const patched = content.replace(
  /\/\/# sourceMappingURL=leo-widget\.js\.map\s*$/m,
  `//# sourceMappingURL=${hashedMap}`
);
writeFileSync(`dist/v1/${hashedJs}`, patched, "utf8");

if (existsSync(SRC_MAP)) {
  copyFileSync(SRC_MAP, `dist/v1/${hashedMap}`);
}

// Record the filename so the GitHub Actions workflow can read it.
writeFileSync("dist/v1/.bundle", hashedJs, "utf8");

console.log(`[hash-bundle] ${SRC_JS} -> dist/v1/${hashedJs}  (hash=${hash})`);
