/**
 * VT-LEO-AI-231 / VT-LEO-AI-509 -- SummarisationContextSelect primitive
 *
 * Pins the contracts of the grouped dropdown (DI-LEO-AI-231 extended,
 * DI-LEO-AI-507) and -- crucially -- enforces frontend / backend
 * enum parity by reading the SummarisationContextValue union from
 * the React primitive and comparing it to the Python enum members.
 *
 * After the secondary-care expansion (UN-LEO-AI-091 / DI-LEO-AI-507):
 *   - The "Acute" group has been renamed to "Secondary care".
 *   - 14 new options have been added (12 secondary-care +
 *     best_interests_dols + mental_health_tribunal).
 *   - Total enum / option count is 35.
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
  // Stop at the next top-level dict / class / def declaration. The
  // first such declaration after the SummarisationContext enum is
  // SUMMARISATION_CONTEXT_GROUPS (added by DI-LEO-AI-507) ahead of
  // SUMMARISATION_CONTEXT_LABELS.
  const stopMatch = tail.match(
    /\n\n(SUMMARISATION_CONTEXT_GROUPS|SUMMARISATION_CONTEXT_LABELS|class |def )/,
  );
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

describe("VT-LEO-AI-509 SummarisationContextSelect primitive (expanded)", () => {
  it("renders a card-grid picker with 4 groups and 35 options", () => {
    const src = read(PRIMITIVE);
    // Groups are declared in SUMMARISATION_CONTEXT_GROUPS and rendered
    // as section blocks of cards inside a Dialog -- count the data
    // array directly so the test is decoupled from the markup.
    const groupNames = src.match(/group:\s*"([^"]+)"/g) ?? [];
    expect(groupNames.length).toBe(4);
    const optionTestIds =
      src.match(/summarisation-context-option-\$\{o\.value\}/g) ?? [];
    expect(optionTestIds.length).toBeGreaterThan(0);
    const valueLines = src.match(/^\s+value:\s*"[a-z_]+"/gm) ?? [];
    expect(valueLines.length).toBe(35);
    // Legacy grouped MUI Select markup is gone -- the picker is now a
    // Dialog, so ListSubheader / MenuItem / FormControl must NOT appear.
    expect(src).not.toContain("<ListSubheader");
    expect(src).not.toContain("<MenuItem");
    expect(src).not.toMatch(/from\s+"@mui\/material\/Select"/);
  });

  it("uses a Dialog with a search field and a CSS grid of cards", () => {
    const src = read(PRIMITIVE);
    // Trigger button + dialog plumbing.
    expect(src).toMatch(/from\s+"@mui\/material\/Dialog"/);
    expect(src).toMatch(/from\s+"@mui\/material\/DialogContent"/);
    expect(src).toMatch(/from\s+"@mui\/material\/DialogTitle"/);
    expect(src).toContain('data-testid="summarisation-context-dialog"');
    expect(src).toContain('data-testid="summarisation-context-open"');
    // Search input that filters labels and descriptions.
    expect(src).toContain('"data-testid": "summarisation-context-search"');
    expect(src).toMatch(/function\s+filterGroups\s*\(/);
    // Grid layout for the cards (responsive, 1 / 2 / 3 columns).
    expect(src).toMatch(/display:\s*"grid"/);
    expect(src).toMatch(/gridTemplateColumns/);
    expect(src).toMatch(/repeat\(2,\s*1fr\)/);
    expect(src).toMatch(/repeat\(3,\s*1fr\)/);
    // Empty / no-match state is reachable.
    expect(src).toContain('data-testid="summarisation-context-no-match"');
    // Cards are buttons (keyboard reachable) with aria-pressed for
    // the selected state.
    expect(src).toMatch(/ButtonBase/);
    expect(src).toMatch(/aria-pressed=\{isSelected\}/);
  });

  it("renames the Acute group to Secondary care", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/group:\s*"Secondary care"/);
    expect(src).not.toMatch(/group:\s*"Acute"/);
  });

  it("uses the four expected group names", () => {
    const src = read(PRIMITIVE);
    const expected = [
      "Primary care",
      "Secondary care",
      "Statutory and social",
      "Quality assurance",
    ];
    for (const name of expected) {
      expect(src).toContain(`group: "${name}"`);
    }
  });

  it("includes the 14 new context options", () => {
    const src = read(PRIMITIVE);
    const newValues = [
      "outpatient_new_clinic",
      "outpatient_followup_clinic",
      "mdt_specialty",
      "pre_op_assessment",
      "procedure_note",
      "ward_round_progress",
      "ed_handover",
      "comprehensive_geriatric_assessment",
      "tertiary_referral",
      "specialty_letter_to_gp",
      "chemotherapy_consent",
      "palliative_care_mdt",
      "best_interests_dols",
      "mental_health_tribunal",
    ];
    for (const v of newValues) {
      expect(src).toContain(`value: "${v}"`);
    }
  });

  it("clarifies the mdt_discussion label as primary care", () => {
    const src = read(PRIMITIVE);
    // Locate the mdt_discussion option block and confirm the label is
    // explicitly tagged as primary care to disambiguate from the new
    // mdt_specialty (secondary care) option.
    const m = src.match(
      /value:\s*"mdt_discussion",[\s\S]*?label:\s*"([^"]+)"/,
    );
    expect(m).not.toBeNull();
    expect(m![1].toLowerCase()).toContain("primary care");
  });

  it("frontend SummarisationContextValue union mirrors libs/sbar/events.SummarisationContext (parity)", () => {
    const tsMembers = extractTsUnionMembers(read(PRIMITIVE));
    const pyMembers = extractPyEnumMembers(read(PY_ENUM));
    expect([...tsMembers].sort()).toEqual([...pyMembers].sort());
    expect(tsMembers.size).toBe(35);
  });
});
