/**
 * VT-LEO-AI-192 -- Dry-run row 'Open in gold editor' + GoldDataset deep-link.
 *
 * Static-source verification per ui-testing.mdc: asserts on the source
 * string of EvaluateStage.tsx, GoldDatasetPanel.tsx, and the
 * /gold-dataset/page.tsx file rather than rendering the components
 * (EvaluateStage hits the network on mount and GoldDatasetPanel needs
 * a Suspense+route context that lives at the page level).
 *
 * Pins DI-LEO-AI-199 / DO-LEO-AI-197.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function readUI(relative: string): string {
  return fs.readFileSync(path.join(ROOT, "services/ui/src", relative), "utf-8");
}

const EVALUATE_SRC = readUI("components/console/EvaluateStage.tsx");
const PANEL_SRC = readUI("components/gold-dataset/GoldDatasetPanel.tsx");
const PAGE_SRC = readUI("app/gold-dataset/page.tsx");

describe("VT-192 -- Dry-run row 'Open in gold editor' + deep link", () => {
  // -- VT-192-TC-001 -------------------------------------------------------
  it("TC-001: EvaluateStage imports IconButton, EditNoteIcon and useRouter", () => {
    expect(EVALUATE_SRC).toMatch(
      /import IconButton from "@mui\/material\/IconButton";/,
    );
    expect(EVALUATE_SRC).toMatch(
      /import EditNoteIcon from "@mui\/icons-material\/EditNote";/,
    );
    expect(EVALUATE_SRC).toMatch(
      /import \{ useRouter \} from "next\/navigation";/,
    );
  });

  // -- VT-192-TC-002 -------------------------------------------------------
  it("TC-002: aria-label='Open in gold editor' appears in both row blocks", () => {
    const matches = EVALUATE_SRC.match(/aria-label="Open in gold editor"/g);
    expect(matches).not.toBeNull();
    expect((matches ?? []).length).toBeGreaterThanOrEqual(2);
  });

  // -- VT-192-TC-003 -------------------------------------------------------
  it("TC-003: handler POSTs to /api/training/candidates/from-dry-run and pushes the deep link", () => {
    expect(EVALUATE_SRC).toContain("/api/training/candidates/from-dry-run");
    expect(EVALUATE_SRC).toMatch(
      /router\.push\(`\/admin\/gold-dataset\?labelId=\$\{[^}]+\}&from=dry_run`\)/,
    );
  });

  // -- VT-192-TC-004 -------------------------------------------------------
  it("TC-004: IconButton disabled prop guards in-flight clicks and empty text", () => {
    expect(EVALUATE_SRC).toMatch(
      /disabled=\{[^}]*!text\.trim\(\)[^}]*openingGoldEditor === row\.encounter_id[^}]*\}/,
    );
  });

  // -- VT-192-TC-005 -------------------------------------------------------
  it("TC-005: GoldDatasetPanel imports useSearchParams/usePathname/useRouter", () => {
    expect(PANEL_SRC).toMatch(
      /import \{[^}]*usePathname[^}]*useRouter[^}]*useSearchParams[^}]*\} from "next\/navigation";/,
    );
  });

  // -- VT-192-TC-006 -------------------------------------------------------
  it("TC-006: deep-link useEffect resolves labelId, opens dialog, clears query", () => {
    expect(PANEL_SRC).toContain("searchParams?.get(\"labelId\")");
    expect(PANEL_SRC).toContain("setSelectedItem");
    expect(PANEL_SRC).toMatch(/router\.replace\(/);
    // Must guard against repeated open after close.
    expect(PANEL_SRC).toMatch(/handledDeepLinkRef/);
  });

  // -- VT-192-TC-007 -------------------------------------------------------
  it("TC-007: from=dry_run switches the panel to the candidates tab", () => {
    expect(PANEL_SRC).toContain("setTab(\"candidates\")");
    expect(PANEL_SRC).toMatch(
      /deepLinkFrom === "dry_run"|searchParams\?\.get\("from"\)[^]*=== "dry_run"/,
    );
  });

  // -- VT-192-TC-008 -------------------------------------------------------
  it("TC-008: /gold-dataset/page.tsx wraps GoldDatasetPanel in <Suspense>", () => {
    expect(PAGE_SRC).toMatch(/import \{ Suspense \} from "react";/);
    expect(PAGE_SRC).toMatch(
      /<Suspense[\s\S]*?>[\s\S]*?<GoldDatasetPanel\s*\/>[\s\S]*?<\/Suspense>/,
    );
  });
});
