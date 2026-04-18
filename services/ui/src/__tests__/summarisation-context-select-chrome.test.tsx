/**
 * VT-LEO-AI-231 -- SummarisationContextSelect primitive
 *
 * Pins the contracts of the grouped dropdown (DI-LEO-AI-231 /
 * DO-LEO-AI-231) and -- crucially -- enforces frontend / backend
 * enum parity by reading the SummarisationContextValue union from
 * the React primitive and comparing it to the Python enum members.
 */
import fs from "fs";
import path from "path";

const PRIMITIVE = path.resolve(
  __dirname,
  "..",
  "components",
  "sbar-playground",
  "SummarisationContextSelect.tsx",
);

const PY_ENUM = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "..",
  "libs",
  "sbar",
  "events.py",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

function extractTsUnionMembers(src: string): Set<string> {
  const m = src.match(
    /export type SummarisationContextValue\s*=([\s\S]*?);/,
  );
  if (!m) throw new Error("SummarisationContextValue union not found");
  const out = new Set<string>();
  for (const lit of m[1].matchAll(/"([a-z0-9_]+)"/g)) {
    out.add(lit[1]);
  }
  return out;
}

function extractPyEnumMembers(src: string): Set<string> {
  // Anchor on the first member assignment after the class header so we
  // scan the enum body itself rather than the docstring (which contains
  // its own blank lines).
  const start = src.indexOf("class SummarisationContext(str, Enum):");
  if (start < 0) throw new Error("SummarisationContext class not found");
  const tail = src.slice(start);
  // Stop at the next top-level dict or class declaration.
  const stopMatch = tail.match(/\n\n(SUMMARISATION_CONTEXT_LABELS|class |def )/);
  const body = stopMatch
    ? tail.slice(0, (stopMatch.index ?? tail.length))
    : tail;
  const out = new Set<string>();
  for (const m of body.matchAll(
    /^ {4}([a-z0-9_]+)\s*=\s*"([a-z0-9_]+)"\s*$/gm,
  )) {
    if (m[1] === m[2]) out.add(m[2]);
  }
  return out;
}

describe("VT-LEO-AI-231 SummarisationContextSelect primitive", () => {
  it("renders a grouped Select with 4 groups and 20 menu options", () => {
    const src = read(PRIMITIVE);
    // Groups are declared in SUMMARISATION_CONTEXT_GROUPS and rendered
    // via flatMap into ListSubheader rows -- count the data array.
    const groupNames = src.match(/group:\s*"([^"]+)"/g) ?? [];
    expect(groupNames.length).toBe(4);
    expect(src).toContain("<ListSubheader");
    const optionTestIds =
      src.match(/summarisation-context-option-\$\{o\.value\}/g) ?? [];
    expect(optionTestIds.length).toBeGreaterThan(0);
    const valueLines = src.match(/^\s+value:\s*"[a-z_]+"/gm) ?? [];
    // 20 enum values + 4 group `value` keys would give 24, but the
    // group object uses `group:` not `value:`. So this counts options.
    expect(valueLines.length).toBe(20);
  });

  it("frontend SummarisationContextValue union mirrors libs/sbar/events.SummarisationContext (parity)", () => {
    const tsMembers = extractTsUnionMembers(read(PRIMITIVE));
    const pyMembers = extractPyEnumMembers(read(PY_ENUM));
    expect([...tsMembers].sort()).toEqual([...pyMembers].sort());
    expect(tsMembers.size).toBe(20);
  });
});
