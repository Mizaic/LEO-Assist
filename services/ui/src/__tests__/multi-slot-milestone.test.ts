// VT-AD52DFB4 -- Multi-slot encounter attach + per-slot detach
//
// Static-source + live checks that a single encounter can fill
// multiple milestone slots on the same episode (DI-F5E030ED). The
// AI engine writer already emits multi-slot encounters via
//   MERGE (e)-[r:IS_PART_OF {milestone_type: $mt}]->(ep)
// These tests pin the UI layer so the manual-curation paths
// (EncounterCard, MilestoneCurationDialog, useMilestoneCuration,
// missionControlApi) agree on the multi-slot shape and never
// silently overwrite an AI-tagged slot.
//
// Atlas trace:
//   UN: UN-5DF22C8F
//   DI: DI-F5E030ED
//   DO: DO-128CB534
//   VT: VT-AD52DFB4

import * as fs from "fs";
import * as path from "path";

import { buildMilestoneLookup } from "../components/mission-control/useMilestoneCuration";
import type { MissionEpisode } from "@/lib/missionControlApi";

const ROOT = path.resolve(__dirname, "../../../..");
const COMPONENT_DIR = path.join(
  ROOT,
  "services/ui/src/components/mission-control"
);
const LIB_DIR = path.join(ROOT, "services/ui/src/lib");

function readComponent(name: string): string {
  return fs.readFileSync(path.join(COMPONENT_DIR, name), "utf-8");
}

function readLib(name: string): string {
  return fs.readFileSync(path.join(LIB_DIR, name), "utf-8");
}

// ---------------------------------------------------------------------------
// Live checks -- buildMilestoneLookup
// ---------------------------------------------------------------------------

describe("VT-AD52DFB4 - buildMilestoneLookup returns array per encounter", () => {
  const episodes: MissionEpisode[] = [
    {
      episode_id: "ep-a",
      status: "active",
      cancer_type: "breast",
      milestones: [
        { encounter_id: "E-1", milestone_type: "first_presentation", date: "2024-08-14" },
        { encounter_id: "E-1", milestone_type: "referral", date: "2024-08-14" },
        { encounter_id: "E-2", milestone_type: "first_seen", date: "2024-09-01" },
      ],
    } as unknown as MissionEpisode,
  ];

  it("TC-005: the same encounter appears under every slot it fills", () => {
    const lookup = buildMilestoneLookup(episodes);
    const e1 = lookup.get("E-1") ?? [];
    const slots = e1.map((e) => e.milestoneType).sort();
    expect(slots).toEqual(["first_presentation", "referral"]);
    expect(e1.every((entry) => entry.episodeId === "ep-a")).toBe(true);
  });

  it("TC-005b: an encounter with a single slot returns a 1-entry array", () => {
    const lookup = buildMilestoneLookup(episodes);
    const e2 = lookup.get("E-2") ?? [];
    expect(e2).toHaveLength(1);
    expect(e2[0].milestoneType).toBe("first_seen");
  });

  it("TC-005c: duplicate (episode, slot) entries are de-duplicated", () => {
    const dupEpisodes: MissionEpisode[] = [
      {
        episode_id: "ep-a",
        status: "active",
        milestones: [
          { encounter_id: "E-1", milestone_type: "first_presentation", date: "2024-08-14" },
          { encounter_id: "E-1", milestone_type: "first_presentation", date: "2024-08-14" },
        ],
      } as unknown as MissionEpisode,
    ];
    const lookup = buildMilestoneLookup(dupEpisodes);
    expect(lookup.get("E-1")).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Static-source checks -- EncounterCard + Dialog + API
// ---------------------------------------------------------------------------

describe("VT-AD52DFB4 - multi-slot UI surfaces", () => {
  it("TC-006: EncounterCard accepts currentMilestoneTypes: string[] and joins labels with ' + '", () => {
    const src = readComponent("EncounterCard.tsx");
    expect(src).toMatch(/currentMilestoneTypes\??:\s*string\[\]\s*\|\s*null/);
    expect(src).toMatch(/linkedSlots\.map\(milestoneLabel\)\.join\(" \+ "\)/);
    // The button renders "Add to milestone" when the array is empty.
    expect(src).toMatch(/hasLinkedSlots\s*\?\s*"contained"\s*:\s*"outlined"/);
    expect(src).toMatch(/linkedSlots\.length\s*===\s*0|linkedSlots\.length\s*>\s*0|hasLinkedSlots/);
  });

  it("TC-007: MilestoneCurationDialog accepts existingLinks[] and renders per-slot chips", () => {
    const dialog = readComponent("MilestoneCurationDialog.tsx");
    const parts = readComponent("MilestoneCurationParts.tsx");
    // Dialog prop shape.
    expect(dialog).toMatch(/existingLinks:\s*ExistingLink\[\]/);
    // PickStage renders one chip per link, each with a Remove button.
    expect(parts).toMatch(/existingLinks\.map\(\(link\)\s*=>/);
    expect(parts).toMatch(/data-testid=\{`milestone-dialog-existing-chip-\$\{link\.milestoneType\}`\}/);
    expect(parts).toMatch(/onDelete=\{\s*busy\s*\?\s*undefined\s*:/);
  });

  it("TC-007b: the dialog title lists every currently-linked slot joined with ' + '", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    expect(src).toMatch(
      /existingLinks[\s\S]{0,80}\.map\([\s\S]{0,80}milestoneLabel[\s\S]{0,80}\.milestoneType[\s\S]{0,40}\)[\s\S]{0,40}\.join\(" \+ "\)/
    );
  });

  it("TC-003/TC-004: detach helpers forward milestoneType as a query param", () => {
    const src = readLib("missionControlApi.ts");
    // Signature carries the optional milestoneType hint.
    expect(src).toMatch(
      /detachEncounterFromEpisode\([\s\S]*?opts\?:[\s\S]*?milestoneType\?:\s*string\s*\|\s*null/
    );
    // Query string is only appended when milestone_type is set.
    expect(src).toMatch(/\?milestone_type=\$\{encodeURIComponent\(mt\)\}/);
    // The day-detach wrapper forwards the slot hint through to the
    // per-encounter helper.
    expect(src).toMatch(
      /detachEncounterFromEpisode\([\s\S]{0,200}milestoneType:\s*body\.milestoneType/
    );
  });

  it("TC-008: dialog picker is multi-select and opens with NO slot AND NO episode pre-selected (DI-74AF7AD8)", () => {
    // DI-F5E030ED multi-select: the picker takes a string[] state.
    // DI-74AF7AD8 no-default: the dialog opens with milestoneTypes
    // = [] AND episodeId = "" (the previous heuristics silently
    // attached to the wrong slot or pathway -- "It keeps adding
    // things I don't want" / "its too easy to addatch to the wrong
    // epside"). The Continue button stays disabled until the
    // curator explicitly picks both an episode and at least one
    // slot.
    const dialog = readComponent("MilestoneCurationDialog.tsx");
    const parts = readComponent("MilestoneCurationParts.tsx");
    const actions = readComponent("MilestoneCurationActions.tsx");
    expect(dialog).toMatch(/useState<string\[\]>\(\[\]\)/);
    // Must NOT auto-pick a slot anywhere in the dialog.
    expect(dialog).not.toMatch(/defaultSlots\(/);
    expect(dialog).toMatch(/setMilestoneTypes\(\[\]\)/);
    // Must NOT seed episodeId from the defaultEpisodeId prop.
    expect(dialog).toMatch(/useState\(""\)/);
    expect(dialog).toMatch(/setEpisodeId\(""\)/);
    expect(dialog).toMatch(/defaultEpisodeId:\s*_defaultEpisodeId/);
    // Continue button is gated on noEpisode as well as noSlot /
    // noneSelected / episodesEmpty.
    expect(dialog).toMatch(/noEpisode=\{!episodeId\}/);
    expect(actions).toMatch(/noEpisode/);
    expect(actions).toMatch(/episodesEmpty\s*\|\|\s*\n?\s*noEpisode/);
    // Episode dropdown carries a disabled placeholder so MUI does
    // not warn about an unmatched value="".
    expect(parts).toMatch(/milestone-dialog-episode-placeholder/);
    expect(parts).toMatch(/displayEmpty:\s*true/);
    expect(parts).toMatch(/multiple:\s*true/);
    expect(parts).toMatch(/linkedOnEpisode\.has\(opt\.value\)/);
    expect(parts).toMatch(/setMilestoneTypes\(next\.filter\(Boolean\)\)/);
  });

  it("TC-009: multi-slot orchestrator aggregates per-slot results with new + already_linked + failed counts", () => {
    const src = readLib("missionControlApi.ts");
    expect(src).toMatch(/attachEncounterDayToMultipleMilestones/);
    expect(src).toMatch(/MilestoneMultiSlotResult/);
    expect(src).toMatch(/newlyLinked/);
    expect(src).toMatch(/alreadyLinked/);
    expect(src).toMatch(/allSucceeded/);
    // Internal: the orchestrator iterates the picked slot list and
    // calls the single-slot helper once per slot.
    expect(src).toMatch(
      /for \(const milestoneType of body\.milestoneTypes\)[\s\S]{0,200}attachEncounterDayToMilestone\(/
    );
    // The single-slot helper now surfaces the backend's
    // already_linked flag per encounter.
    expect(src).toMatch(/if \(res\.already_linked\) alreadyLinked\.push/);
  });

  it("TC-002: idempotent re-attach short-circuits via already_linked flag", () => {
    // The helper short-circuits before any AuditEvent write when the
    // (encounter, episode, slot) edge already exists on the graph.
    // The backend owns the flag; the UI simply tolerates an
    // already_linked=true response body from the existing attach
    // helper without diverging its call-site code.
    const src = readLib("missionControlApi.ts");
    expect(src).toMatch(/attachEncounterToEpisode/);
    // No new UI-side short-circuit code is required -- the day
    // wrapper iterates per-encounter regardless.
    expect(src).toMatch(/for \(const encounterId of body\.encounterIds\)/);
  });
});
