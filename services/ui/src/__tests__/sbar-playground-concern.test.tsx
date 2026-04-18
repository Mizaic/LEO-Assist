/**
 * VT-LEO-AI-233 -- SbarPlayground Concern field contract
 *
 * Pins the UI side of the two-sided 500-character cap on the
 * QSIR-aligned Concern field (DI-LEO-AI-233 / DO-LEO-AI-233):
 *   - the textarea has maxLength=500
 *   - a visible character counter is rendered
 *   - the Concern is forwarded to useSbarStream as `concern`
 */
import fs from "fs";
import path from "path";

const PLAYGROUND = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "ai-summarisation",
  "SbarPlayground.tsx",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-233 SbarPlayground Concern field", () => {
  it("defines a 500-character cap constant", () => {
    const src = read(PLAYGROUND);
    expect(src).toMatch(/CONCERN_MAX_CHARS\s*=\s*500/);
  });

  it("textarea has maxLength=CONCERN_MAX_CHARS and a visible counter", () => {
    const src = read(PLAYGROUND);
    expect(src).toMatch(/maxLength:\s*CONCERN_MAX_CHARS/);
    expect(src).toMatch(/\$\{concern\.length\}\s*\/\s*\$\{CONCERN_MAX_CHARS\}/);
  });

  it("forwards the concern to useSbarStream.start", () => {
    const src = read(PLAYGROUND);
    expect(src).toMatch(/concern:\s*concern\.trim\(\)\s*\|\|\s*undefined/);
  });
});
