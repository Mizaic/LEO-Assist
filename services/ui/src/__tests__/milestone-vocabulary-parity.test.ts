// VT-900E2453 -- Milestone vocabulary parity (front-end half)
//
// Static-source verification that the manual-curation milestone slot
// picker is locked to the canonical nine values that the AI engine
// can emit (eight from services/analysis_worker/app/episode_engine/
// schemas.py Milestone.type Literal plus care_obstruction emitted by
// services/analysis_worker/app/analyzers/anchor_detector.py), with
// first_seen labelled "First seen by specialist".
//
// The companion backend half is in
// tests/test_episode_crud_endpoints.py::TestMilestoneVocabularyParity.
// Together they fail the build the moment the picker, the helpers
// allow-list, the dashboards edit_milestone allow-list, or the engine
// schema drift apart.
//
// These checks read the source as text and assert structural
// invariants -- no network, no React render.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const COMPONENT_DIR = path.join(
  ROOT,
  "services/ui/src/components/mission-control"
);

function readComponent(name: string): string {
  return fs.readFileSync(path.join(COMPONENT_DIR, name), "utf-8");
}

// The pathway tier (canonical nine) -- AI engine emits these and
// they feed episode date roll-ups. Order matters because the picker
// presents them top-to-bottom in cancer-pathway sequence.
const PATHWAY_VALUES = [
  "first_presentation",
  "referral",
  "first_seen",
  "outcome_letter",
  "diagnosis_confirmed",
  "treatment_started",
  "treatment_completed",
  "benign_closure",
  "care_obstruction",
] as const;

// The context tier (DI-50C7E89C) -- supporting evidence the curator
// can attach but the AI engine does NOT emit. Never feeds date
// roll-ups; descriptive only.
const CONTEXT_VALUES = [
  "related_gp_visit",
  "primary_care_investigations",
  "referral_admin",
  "referral_sent",
  "related_specialist_visit",
  "specialist_diagnostics",
  "related_correspondence",
  "treatment_planned",
  "treatment_monitoring",
  "treatment_toxicity",
] as const;

// Legacy values that MUST NOT appear in the picker, but whose edges
// may still exist on historical episodes and must keep rendering via
// milestoneLabel(). Note: referral_sent has been promoted out of
// this list into CONTEXT_VALUES.
const LEGACY_VALUES = [
  "presentation",
  "specialist_visit",
  "first_clinic_visit",
  "clinic_visit",
  "first_clinic",
  "investigation",
  "diagnosis",
  "treatment_decision",
  "treatment",
  "first_treatment",
  "related",
] as const;

describe("VT-900E2453 - milestone vocabulary parity", () => {
  it("VT-900E2453-TC-001: MILESTONE_OPTIONS lists pathway tier first, then context tier, in declared order", () => {
    const src = readComponent("milestoneOptions.ts");
    const arrMatch = src.match(
      /export const MILESTONE_OPTIONS:[^=]*=\s*\[([\s\S]*?)\];/
    );
    expect(arrMatch).not.toBeNull();
    const body = arrMatch![1];
    const valueMatches = [...body.matchAll(/value:\s*"([^"]+)"/g)].map(
      (m) => m[1]
    );
    expect(valueMatches).toEqual([
      ...PATHWAY_VALUES,
      ...CONTEXT_VALUES,
    ]);
  });

  it("VT-900E2453-TC-001a: every option declares a group of either 'pathway' or 'context'", () => {
    const src = readComponent("milestoneOptions.ts");
    const arrMatch = src.match(
      /export const MILESTONE_OPTIONS:[^=]*=\s*\[([\s\S]*?)\];/
    );
    expect(arrMatch).not.toBeNull();
    const body = arrMatch![1];
    // One group: token per option entry. Count must equal the
    // total number of options so the picker subheaders cannot drift.
    const groupTokens = [...body.matchAll(/group:\s*"([a-z]+)"/g)].map(
      (m) => m[1]
    );
    const total = PATHWAY_VALUES.length + CONTEXT_VALUES.length;
    expect(groupTokens.length).toBe(total);
    expect(new Set(groupTokens)).toEqual(new Set(["pathway", "context"]));
    // The first PATHWAY_VALUES.length entries must be the pathway tier
    // and the rest must be the context tier (declared order matters).
    expect(groupTokens.slice(0, PATHWAY_VALUES.length)).toEqual(
      Array(PATHWAY_VALUES.length).fill("pathway")
    );
    expect(groupTokens.slice(PATHWAY_VALUES.length)).toEqual(
      Array(CONTEXT_VALUES.length).fill("context")
    );
  });

  it("VT-900E2453-TC-002: first_seen is labelled 'First seen by specialist' and legacy values are gone", () => {
    const src = readComponent("milestoneOptions.ts");
    expect(src).toMatch(
      /value:\s*"first_seen",\s*label:\s*"First seen by specialist"/
    );
    for (const legacy of LEGACY_VALUES) {
      expect(src).not.toMatch(
        new RegExp(`value:\\s*"${legacy}"`),
      );
    }
  });

  it("VT-900E2453-TC-003: CreateEpisodeDialog imports MILESTONE_OPTIONS from milestoneOptions and does not redeclare it", () => {
    const src = readComponent("CreateEpisodeDialog.tsx");
    expect(src).toMatch(
      /import\s+\{\s*MILESTONE_OPTIONS\s*\}\s+from\s+"\.\/milestoneOptions"/
    );
    // The inline array literal must be gone -- there is no second
    // `const MILESTONE_OPTIONS = [` declaration in this file.
    const decls = src.match(/const\s+MILESTONE_OPTIONS\s*=/g);
    expect(decls).toBeNull();
    // Default for the create-form milestone slot must be a canonical
    // value (the legacy "presentation" default is gone).
    expect(src).toMatch(/initialMilestoneType:\s*"first_presentation"/);
    expect(src).not.toMatch(/initialMilestoneType:\s*"presentation"/);
  });

  it("VT-900E2453-TC-004: backend PATHWAY/CONTEXT/MILESTONE_TYPES tiers match the front-end picker exactly", () => {
    const src = fs.readFileSync(
      path.join(
        ROOT,
        "services/analytics_api/app/routers/_episode_crud_helpers.py"
      ),
      "utf-8"
    );
    const pathwayBlock = src.match(
      /PATHWAY_MILESTONE_TYPES:\s*frozenset\[str\]\s*=\s*frozenset\(\s*\{([\s\S]*?)\}\s*\)/
    );
    expect(pathwayBlock).not.toBeNull();
    const pathwayValues = [
      ...pathwayBlock![1].matchAll(/"([a-z_]+)"/g),
    ].map((m) => m[1]);
    expect(new Set(pathwayValues)).toEqual(new Set(PATHWAY_VALUES));
    expect(pathwayValues.length).toBe(PATHWAY_VALUES.length);

    const contextBlock = src.match(
      /CONTEXT_MILESTONE_TYPES:\s*frozenset\[str\]\s*=\s*frozenset\(\s*\{([\s\S]*?)\}\s*\)/
    );
    expect(contextBlock).not.toBeNull();
    const contextValues = [
      ...contextBlock![1].matchAll(/"([a-z_]+)"/g),
    ].map((m) => m[1]);
    expect(new Set(contextValues)).toEqual(new Set(CONTEXT_VALUES));
    expect(contextValues.length).toBe(CONTEXT_VALUES.length);

    // MILESTONE_TYPES is computed from the union of the two tiers --
    // the source must say so explicitly so the union cannot drift.
    expect(src).toMatch(
      /MILESTONE_TYPES:\s*frozenset\[str\]\s*=\s*\(?\s*PATHWAY_MILESTONE_TYPES\s*\|\s*CONTEXT_MILESTONE_TYPES\s*\)?/
    );
  });

  it("VT-900E2453-TC-005: dashboards.edit_milestone validates against the imported MILESTONE_TYPES (no inline literal set)", () => {
    const src = fs.readFileSync(
      path.join(
        ROOT,
        "services/analytics_api/app/routers/dashboards.py"
      ),
      "utf-8"
    );
    expect(src).toMatch(
      /from \._episode_crud_helpers import MILESTONE_TYPES/
    );
    expect(src).toMatch(/body\.milestone_type not in MILESTONE_TYPES/);
    // The legacy inline valid_types literal block is gone -- none of
    // these strings should appear as Python literals here any more.
    expect(src).not.toMatch(/"first_clinic_visit"/);
    expect(src).not.toMatch(/"specialist_visit"/);
    expect(src).not.toMatch(/"referral_sent"/);
  });

  it("VT-900E2453-TC-006: engine schema Milestone.type Literal covers the full 15 values (8 pathway + 7 context)", () => {
    // Policy change: DI-2C015ADE supersedes DI-50C7E89C. The AI
    // engine now emits context-tier milestones; presence forces
    // the episode's confidence_tier off "auto" so every emission
    // is human-reviewed (see voting.assign_confidence_tier).
    // care_obstruction is still emitted by the anchor detector,
    // not the LLM, so it stays out of Milestone.type.
    const schemaSrc = fs.readFileSync(
      path.join(
        ROOT,
        "services/analysis_worker/app/episode_engine/schemas.py"
      ),
      "utf-8"
    );
    const milestoneClass = schemaSrc.match(
      /class Milestone\(BaseModel\):[\s\S]*?type:\s*Literal\[([\s\S]*?)\]/
    );
    expect(milestoneClass).not.toBeNull();
    const literalBody = milestoneClass![1];
    const values = [...literalBody.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
    const pathwayLLM = PATHWAY_VALUES.filter((v) => v !== "care_obstruction");
    const expected = [...pathwayLLM, ...CONTEXT_VALUES];
    expect(new Set(values)).toEqual(new Set(expected));
    expect(values.length).toBe(expected.length);
    // Reverse drift guard: care_obstruction still must NOT appear
    // in the LLM schema -- it is an anchor-detector output.
    expect(literalBody).not.toMatch(/"care_obstruction"/);
  });

  it("VT-900E2453-TC-006a: engine schema declares PATHWAY_MILESTONE_TYPES and CONTEXT_MILESTONE_TYPES tuples that match the UI vocabulary", () => {
    // The two tuples are imported by prompts and the writer so they
    // cannot drift from the Literal.
    const schemaSrc = fs.readFileSync(
      path.join(
        ROOT,
        "services/analysis_worker/app/episode_engine/schemas.py"
      ),
      "utf-8"
    );
    const pathwayTuple = schemaSrc.match(
      /PATHWAY_MILESTONE_TYPES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\(([\s\S]*?)\)/
    );
    expect(pathwayTuple).not.toBeNull();
    const pathwayValues = [
      ...pathwayTuple![1].matchAll(/"([a-z_]+)"/g),
    ].map((m) => m[1]);
    const pathwayLLM = PATHWAY_VALUES.filter((v) => v !== "care_obstruction");
    expect(new Set(pathwayValues)).toEqual(new Set(pathwayLLM));

    const contextTuple = schemaSrc.match(
      /CONTEXT_MILESTONE_TYPES:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\(([\s\S]*?)\)/
    );
    expect(contextTuple).not.toBeNull();
    const contextValues = [
      ...contextTuple![1].matchAll(/"([a-z_]+)"/g),
    ].map((m) => m[1]);
    expect(new Set(contextValues)).toEqual(new Set(CONTEXT_VALUES));
  });

  it("VT-900E2453-TC-007: _TREATMENT_MILESTONES roll-up set includes treatment_completed", () => {
    const src = fs.readFileSync(
      path.join(
        ROOT,
        "services/analytics_api/app/routers/_episode_crud_helpers.py"
      ),
      "utf-8"
    );
    const block = src.match(/_TREATMENT_MILESTONES\s*=\s*\{([\s\S]*?)\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toMatch(/"treatment_completed"/);
  });

  it("VT-900E2453-TC-008: milestoneLabel falls back to underscore-replace so legacy edges still render", () => {
    const src = readComponent("milestoneOptions.ts");
    expect(src).toMatch(/value\.replaceAll\("_", " "\)/);
  });

  it("VT-900E2453-TC-009: picker renders grouped subheaders and tags each MenuItem with data-milestone-group", () => {
    const src = readComponent("MilestoneCurationParts.tsx");
    // ListSubheader is imported and used per tier.
    expect(src).toMatch(/import\s+ListSubheader\s+from\s+"@mui\/material\/ListSubheader"/);
    expect(src).toMatch(/data-testid=\{`milestone-dialog-slot-subheader-\$\{tier\}`\}/);
    // Each MenuItem carries its tier so headless tests and analytics
    // can distinguish pathway vs context selections without parsing
    // the visible label.
    expect(src).toMatch(/data-milestone-group=\{opt\.group\}/);
    // The render helper iterates pathway then context (in that order)
    // so the picker reads the same way the canonical list is declared.
    expect(src).toMatch(
      /tiers:\s*MilestoneGroup\[\]\s*=\s*\["pathway",\s*"context"\]/
    );
    // The group-label header text comes from MILESTONE_GROUP_LABEL,
    // not a hard-coded string, so the labels stay in one place.
    expect(src).toMatch(/MILESTONE_GROUP_LABEL\[tier\]/);
  });

  it("VT-900E2453-TC-010: MILESTONE_GROUP_LABEL is exported with friendly tier labels", () => {
    const src = readComponent("milestoneOptions.ts");
    expect(src).toMatch(
      /export const MILESTONE_GROUP_LABEL:\s*Record<MilestoneGroup,\s*string>/
    );
    // Must distinguish AI-populated from manual-only so reviewers
    // immediately see which tier they are picking from.
    expect(src).toMatch(/pathway:\s*"Pathway events \(AI also fills these\)"/);
    expect(src).toMatch(
      /context:\s*"Supporting context \(AI suggests, curator confirms\)"/
    );
  });
});
