/**
 * Static-source VT for ReconcilePathwayDrawer.tsx and the helper
 * components it composes (MilestoneSlotRow, BucketFlipWarning,
 * LockChip).
 *
 * Atlas trace:
 *   DO: services/ui/src/components/mission-control/ReconcilePathwayDrawer.tsx
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 *   DI: DI-C424BB44 (VerificationLock primitive)
 *   VT: this file (chrome) + ReconcilePathwayDrawer-confirm.test.tsx
 *
 * Why static-source: the drawer pulls fetch on submit and uses the
 * MUI Drawer portal. Both are awkward under jsdom; the structural
 * invariants we care about (gated buttons, type-the-name field,
 * single primary action, audit-notes textarea) are visible in source.
 */

import { readFileSync } from "fs";
import { resolve } from "path";

const COMP = resolve(
  __dirname,
  "../../components/mission-control/ReconcilePathwayDrawer.tsx"
);
const ROW = resolve(
  __dirname,
  "../../components/mission-control/MilestoneSlotRow.tsx"
);
const WARN = resolve(
  __dirname,
  "../../components/mission-control/BucketFlipWarning.tsx"
);
const CHIP = resolve(
  __dirname,
  "../../components/mission-control/LockChip.tsx"
);
const PANEL = resolve(
  __dirname,
  "../../components/mission-control/ReviewActionsPanel.tsx"
);

const drawer = readFileSync(COMP, "utf8");
const row = readFileSync(ROW, "utf8");
const warn = readFileSync(WARN, "utf8");
const chip = readFileSync(CHIP, "utf8");
const panel = readFileSync(PANEL, "utf8");

describe("ReconcilePathwayDrawer chrome -- DI-9DCC9F84", () => {
  test("imports the API client + helper components it needs", () => {
    expect(drawer).toContain('from "@/lib/missionControlApi"');
    expect(drawer).toContain("patchEpisodeReconcile");
    expect(drawer).toContain('from "./BucketFlipWarning"');
    expect(drawer).toContain('from "./MilestoneSlotRow"');
  });

  test("renders the type-the-name confirm gate via BucketFlipWarning", () => {
    expect(drawer).toContain("<BucketFlipWarning");
    expect(warn).toContain("typed");
    expect(warn).toContain("data-testid=\"bucket-flip-warning\"");
    // Inside MUI inputProps the testid is set via the quoted-key form.
    expect(warn).toContain("\"data-testid\": \"bucket-flip-typed\"");
    expect(warn).toMatch(/bucketMatch/);
  });

  test("Confirm button is disabled until reason and (if needed) flip type-the-name match", () => {
    expect(drawer).toMatch(
      /canSubmit\s*=\s*[^;]*reason\.trim\(\)\.length\s*>\s*0[^;]*flipConfirmed/
    );
    expect(drawer).toContain("disabled={!canSubmit}");
    expect(drawer).toContain('data-testid="reconcile-confirm-button"');
  });

  test("submits a single PATCH containing every staged action and the bucket-flip flag", () => {
    expect(drawer).toContain("await patchEpisodeReconcile(episode.episode_id, body)");
    expect(drawer).toContain("confirm_bucket_flip: flipPending");
    expect(drawer).toContain("actions: Object.values(staged).map");
  });

  test("audit-notes textarea is required and labelled", () => {
    expect(drawer).toContain('label="Reviewer notes (audit trail)"');
    expect(drawer).toContain("required");
    expect(drawer).toContain('"aria-label": "Reviewer notes"');
  });

  test("single primary action -- one variant=contained button in the drawer", () => {
    const matches = drawer.match(/variant=\"contained\"/g) ?? [];
    expect(matches.length).toBe(1);
  });

  test("MilestoneSlotRow exposes Confirm/Replace/Detach/Not applicable", () => {
    // ACTION_LABELS keys appear as bare identifiers in object literal,
    // confirm/replace/detach are quoted only inside the conditional
    // setting encounterId.
    expect(row).toMatch(/confirm:\s*"Confirm"/);
    expect(row).toMatch(/replace:\s*"Replace"/);
    expect(row).toMatch(/detach:\s*"Detach"/);
    expect(row).toMatch(/not_applicable:\s*"Not applicable"/);
  });

  test("LockChip exposes both locked and unlocked visuals with aria labels", () => {
    expect(chip).toContain("LockOutlined");
    expect(chip).toContain("LockOpenOutlined");
    expect(chip).toContain("aria-label");
  });

  test("Drawer is mounted from ReviewActionsPanel only when status==='review' AND role is reviewer", () => {
    expect(panel).toContain('useRole');
    expect(panel).toContain("STATUS_REVIEW");
    expect(panel).toMatch(/reviewerRole\s*!==\s*null/);
    expect(panel).toMatch(
      /selectedRole\s*===\s*"clinician"\s*\|\|\s*selectedRole\s*===\s*"qa_ra_lead"/
    );
    expect(panel).toContain("<ReconcilePathwayDrawer");
    expect(panel).toContain("data-testid=\"open-reconcile-drawer\"");
  });

  test("audit notes are preserved on the request body so the API can persist them with the lock", () => {
    // The body uses object shorthand for `reason`; the explicit
    // mappings appear for the email and role pulled from props.
    expect(drawer).toMatch(/^\s*reason,\s*$/m);
    expect(drawer).toMatch(/reviewed_by:\s*reviewerEmail/);
    expect(drawer).toMatch(/reviewer_role:\s*reviewerRole/);
  });

  test("Atlas trace headers are present in every new component", () => {
    for (const src of [drawer, row, warn, chip]) {
      expect(src).toContain("DI-C424BB44");
      expect(src).toContain("DI-9DCC9F84");
    }
  });
});
