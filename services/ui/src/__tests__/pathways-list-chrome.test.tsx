/**
 * VT-LEO-AI-151 -- Pathways list page Wave E Phase 6 chrome.
 *
 * Static-source verification:
 *   - Page imports design-system StatHero, SegmentedTabs, ToolbarActions.
 *   - Templates, dialogs, PathwayCard, types live in sibling modules.
 *   - PathwayCard uses the canonical 12px / 18px / 3px-accent pattern
 *     and motion stagger.
 *   - All four PATHWAY_TEMPLATES still ship (blank, extraction-only,
 *     extraction-verify-persist, training-audit) so the New Pathway
 *     dialog continues to offer the full menu.
 *   - The single primary action is "New pathway"; status filter is
 *     SegmentedTabs not raw chips.
 *   - Existing data + routing handlers are preserved.
 *
 * Design Controls: DI-LEO-AI-153, DO-LEO-AI-149, VT-LEO-AI-151.
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const PAGE = path.join(ROOT, "services/ui/src/app/admin/pathways/page.tsx");
const HOOK = path.join(ROOT, "services/ui/src/app/admin/pathways/usePathwaysList.ts");
const CARD = path.join(ROOT, "services/ui/src/app/admin/pathways/PathwayCard.tsx");
const PARTS = path.join(ROOT, "services/ui/src/app/admin/pathways/PathwayCardParts.tsx");
const DIALOGS = path.join(ROOT, "services/ui/src/app/admin/pathways/dialogs.tsx");
const TEMPLATES = path.join(ROOT, "services/ui/src/app/admin/pathways/templates.ts");

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-151 - Pathways list chrome", () => {
  test("TC-001: page imports design-system primitives and sibling modules", () => {
    const src = read(PAGE) + read(HOOK);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/StatHero/);
    expect(src).toMatch(/SegmentedTabs/);
    expect(src).toMatch(/ToolbarActions/);
    expect(src).toMatch(/from\s+["']\.\/PathwayCard["']/);
    expect(src).toMatch(/from\s+["']\.\/dialogs["']/);
    expect(src).toMatch(/from\s+["']\.\/types["']/);
    expect(src).toMatch(/from\s+["']\.\/templates["']/);
  });

  test("TC-002: removes legacy custom h5 page header in favour of StatHero", () => {
    const src = read(PAGE);
    expect(src).not.toMatch(/Typography\s+variant="h5"\s+fontWeight=\{700\}>Clinical Pathways/);
    expect(src).toMatch(/<StatHero stats=\{(?:page\.)?stats\}\s*\/>/);
  });

  test("TC-003: preserves /fhir/PlanDefinition data + routing handlers", () => {
    const src = read(PAGE) + read(HOOK);
    expect(src).toMatch(/\.get<[\s\S]*?\(\s*"\/fhir\/PlanDefinition"/);
    expect(src).toMatch(/api\.put\(`\/fhir\/PlanDefinition\/\$\{[^}]+\}`/);
    expect(src).toMatch(/api\.post<[\s\S]*?\(\s*"\/fhir\/PlanDefinition"/);
    expect(src).toMatch(/api\.delete\(`\/fhir\/PlanDefinition\/\$\{[^}]+\}`/);
    expect(src).toMatch(/router\.push\(`\/admin\/pathways\/\$\{[^}]+\}`/);
  });

  test("TC-004: status filter uses SegmentedTabs with the correct API", () => {
    const src = read(PAGE);
    const seg = src.match(/<SegmentedTabs[\s\S]*?\/>/);
    expect(seg).not.toBeNull();
    expect(seg![0]).toMatch(/tabs=\{/);
    expect(seg![0]).toMatch(/value=\{(?:page\.)?statusFilter\}/);
    expect(seg![0]).toMatch(/aria-label="Filter pathways by status"/);
    expect(seg![0]).not.toMatch(/\bitems=/);
    expect(seg![0]).toMatch(/id:\s*"all"/);
    expect(seg![0]).toMatch(/id:\s*"active"/);
    expect(seg![0]).toMatch(/id:\s*"draft"/);
    expect(seg![0]).toMatch(/id:\s*"retired"/);
  });

  test("TC-005: single primary action is 'New pathway'", () => {
    const src = read(PAGE);
    const toolbar = src.match(/toolbarActions:\s*ToolbarAction\[\]\s*=\s*\[[\s\S]*?\];/m);
    expect(toolbar).not.toBeNull();
    expect(toolbar![0]).toMatch(/label:\s*"New pathway"/);
    expect(toolbar![0]).toMatch(/variant:\s*"primary"/);
    const primaryCount = (toolbar![0].match(/variant:\s*"primary"/g) || []).length;
    expect(primaryCount).toBe(1);
  });

  test("TC-006: stats include the four canonical tiles", () => {
    const src = read(HOOK);
    const stats = src.match(/computeStats[\s\S]*?return\s*\[[\s\S]*?\];/m);
    expect(stats).not.toBeNull();
    expect(stats![0]).toMatch(/id:\s*"total"/);
    expect(stats![0]).toMatch(/id:\s*"live"/);
    expect(stats![0]).toMatch(/id:\s*"draft"/);
    expect(stats![0]).toMatch(/id:\s*"retired"/);
  });

  test("TC-007: PathwayCard uses 12px radius and 3px tone-coded accent strip", () => {
    const src = read(CARD);
    expect(src).toMatch(/borderRadius:\s*12,/);
    expect(src).toMatch(/padding:\s*18,/);
    expect(src).toMatch(/width:\s*3,/);
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/fm\.div/);
  });

  test("TC-008: PathwayCard preserves the full action surface", () => {
    const src = read(CARD) + read(PARTS);
    expect(src).toMatch(/onEdit/);
    expect(src).toMatch(/onPublish/);
    expect(src).toMatch(/onDuplicate/);
    expect(src).toMatch(/onRetire/);
    expect(src).toMatch(/onReactivate/);
    expect(src).toMatch(/onDelete/);
    expect(src).toMatch(/disabled=\{busy \|\| isSeeded\}/);
  });

  test("TC-009: dialogs module exports New / Publish / Delete dialogs", () => {
    const src = read(DIALOGS);
    expect(src).toMatch(/export function NewPathwayDialog/);
    expect(src).toMatch(/export function PublishDialog/);
    expect(src).toMatch(/export function DeletePathwayDialog/);
    expect(src).toMatch(/Type the pathway name exactly/);
  });

  test("TC-010: templates module ships all four starter templates", () => {
    const src = read(TEMPLATES);
    expect(src).toMatch(/id:\s*"blank"/);
    expect(src).toMatch(/id:\s*"extraction-only"/);
    expect(src).toMatch(/id:\s*"extraction-verify-persist"/);
    expect(src).toMatch(/id:\s*"training-audit"/);
    expect(src).toMatch(/event:\s*"encounter-created"/);
    expect(src).toMatch(/event:\s*"training-candidate-ready"/);
  });

  test("TC-011: empty / loading / no-match states reachable", () => {
    const src = read(PAGE);
    expect(src).toMatch(/Loading pathways\.\.\./);
    expect(src).toMatch(/No pathways configured yet/);
    expect(src).toMatch(/No pathways match this filter/);
  });
});
