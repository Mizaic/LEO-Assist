import {
  assessPathwayRisk,
  summariseCaseload,
  sortByUrgency,
  groupByPatient,
  daysBetween,
  type Episode,
  type EpisodeWithRisk,
} from "@/lib/pathwayRisk";

const TODAY = "2026-02-26";

function makeEpisode(overrides: Partial<Episode> = {}): Episode {
  return {
    episode_id: "EP-001",
    cancer_type: "Breast",
    status: "active",
    referral_date: "2026-02-01",
    milestones: [],
    ...overrides,
  };
}

describe("daysBetween", () => {
  it("returns positive days for later date", () => {
    expect(daysBetween("2026-01-01", "2026-01-15")).toBe(14);
  });

  it("returns zero for same date", () => {
    expect(daysBetween("2026-01-01", "2026-01-01")).toBe(0);
  });

  it("returns negative for earlier date", () => {
    expect(daysBetween("2026-01-15", "2026-01-01")).toBe(-14);
  });
});

describe("assessPathwayRisk", () => {
  it("marks completed pathway as completed when no breaches", () => {
    const ep = makeEpisode({
      status: "completed",
      referral_date: "2026-01-01",
      milestones: [
        { encounter_id: "E1", date: "2026-01-01", milestone_type: "referral" },
        { encounter_id: "E2", date: "2026-01-10", milestone_type: "first_clinic" },
        { encounter_id: "E3", date: "2026-01-20", milestone_type: "diagnosis" },
        { encounter_id: "E4", date: "2026-02-15", milestone_type: "first_treatment" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("completed");
    expect(risk.worstBreach).toBeNull();
  });

  it("marks completed pathway as breached when RTT exceeded", () => {
    const ep = makeEpisode({
      status: "completed",
      referral_date: "2025-10-01",
      milestones: [
        { encounter_id: "E1", date: "2025-10-01", milestone_type: "referral" },
        { encounter_id: "E2", date: "2025-10-10", milestone_type: "first_clinic" },
        { encounter_id: "E3", date: "2025-11-15", milestone_type: "diagnosis" },
        { encounter_id: "E4", date: "2026-01-15", milestone_type: "first_treatment" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("breached");
    expect(risk.worstBreach).not.toBeNull();
  });

  it("returns on-track for recently referred pathway", () => {
    const ep = makeEpisode({
      referral_date: "2026-02-24",
      milestones: [
        { encounter_id: "E1", date: "2026-02-24", milestone_type: "referral" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("on-track");
    expect(risk.nextExpectedMilestone).toBe("presentation");
  });

  it("returns at-risk when approaching 2WW breach", () => {
    const ep = makeEpisode({
      referral_date: "2026-02-14",
      milestones: [
        { encounter_id: "E1", date: "2026-02-14", milestone_type: "referral" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("at-risk");
  });

  it("returns breached when past 2WW with no first_clinic", () => {
    const ep = makeEpisode({
      referral_date: "2026-02-01",
      milestones: [
        { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("breached");
    expect(risk.worstBreach?.target.label).toBe("2WW");
  });

  it("returns unknown when no referral date", () => {
    const ep = makeEpisode({
      referral_date: undefined,
      milestones: [],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("unknown");
  });

  it("identifies next expected milestone correctly", () => {
    const ep = makeEpisode({
      referral_date: "2026-02-20",
      milestones: [
        { encounter_id: "E1", date: "2026-02-18", milestone_type: "presentation" },
        { encounter_id: "E2", date: "2026-02-20", milestone_type: "referral" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.nextExpectedMilestone).toBe("first_clinic");
  });

  it("uses referral_date when milestones lack explicit referral", () => {
    const ep = makeEpisode({
      referral_date: "2026-02-01",
      milestones: [],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    expect(risk.level).toBe("breached");
    expect(risk.breaches.length).toBeGreaterThan(0);
    const tww = risk.breaches.find((b) => b.target.label === "2WW");
    expect(tww?.daysElapsed).toBe(25);
  });

  it("does not flag achieved targets as breached when within limit", () => {
    const ep = makeEpisode({
      referral_date: "2026-02-01",
      milestones: [
        { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
        { encounter_id: "E2", date: "2026-02-10", milestone_type: "first_clinic" },
      ],
    });
    const risk = assessPathwayRisk(ep, TODAY);
    const tww = risk.breaches.find((b) => b.target.label === "2WW");
    expect(tww?.achieved).toBe(true);
    expect(tww?.breached).toBe(false);
  });
});

describe("summariseCaseload", () => {
  it("counts each risk level", () => {
    const episodes: Episode[] = [
      makeEpisode({ episode_id: "EP-1", referral_date: "2026-02-01" }),
      makeEpisode({ episode_id: "EP-2", referral_date: "2026-02-24" }),
      makeEpisode({
        episode_id: "EP-3",
        status: "completed",
        referral_date: "2026-01-01",
        milestones: [
          { encounter_id: "E1", date: "2026-01-01", milestone_type: "referral" },
          { encounter_id: "E2", date: "2026-01-08", milestone_type: "first_clinic" },
          { encounter_id: "E3", date: "2026-01-20", milestone_type: "diagnosis" },
          { encounter_id: "E4", date: "2026-02-10", milestone_type: "first_treatment" },
        ],
      }),
    ];

    const summary = summariseCaseload(episodes, TODAY);
    expect(summary.total).toBe(3);
    expect(summary.breached).toBe(1);
    expect(summary.onTrack).toBe(1);
    expect(summary.completed).toBe(1);
  });

  it("handles empty list", () => {
    const summary = summariseCaseload([], TODAY);
    expect(summary.total).toBe(0);
    expect(summary.breached).toBe(0);
  });
});

describe("sortByUrgency", () => {
  it("puts breached pathways first", () => {
    const episodes: Episode[] = [
      makeEpisode({ episode_id: "TRACK", referral_date: "2026-02-24" }),
      makeEpisode({ episode_id: "BREACH", referral_date: "2026-01-01" }),
      makeEpisode({
        episode_id: "DONE",
        status: "completed",
        referral_date: "2026-01-01",
        milestones: [
          { encounter_id: "E1", date: "2026-01-01", milestone_type: "referral" },
          { encounter_id: "E2", date: "2026-01-08", milestone_type: "first_clinic" },
          { encounter_id: "E3", date: "2026-01-20", milestone_type: "diagnosis" },
          { encounter_id: "E4", date: "2026-02-10", milestone_type: "first_treatment" },
        ],
      }),
    ];

    const sorted = sortByUrgency(episodes, TODAY);
    expect(sorted[0].episode_id).toBe("BREACH");
    expect(sorted[sorted.length - 1].episode_id).toBe("DONE");
  });

  it("attaches risk to each episode", () => {
    const episodes: Episode[] = [
      makeEpisode({ episode_id: "A", referral_date: "2026-02-24" }),
    ];
    const sorted = sortByUrgency(episodes, TODAY);
    expect(sorted[0].risk).toBeDefined();
    expect(sorted[0].risk.level).toBe("on-track");
  });
});

function withRisk(ep: Episode): EpisodeWithRisk {
  return { ...ep, risk: assessPathwayRisk(ep, TODAY) };
}

describe("groupByPatient", () => {
  it("groups episodes by patient_id", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-1", patient_id: "PAT-A", referral_date: "2026-02-24" })),
      withRisk(makeEpisode({ episode_id: "EP-2", patient_id: "PAT-A", referral_date: "2026-02-20" })),
      withRisk(makeEpisode({ episode_id: "EP-3", patient_id: "PAT-B", referral_date: "2026-02-22" })),
    ];

    const groups = groupByPatient(episodes);
    expect(groups.length).toBe(2);

    const patA = groups.find((g) => g.patientId === "PAT-A");
    expect(patA?.episodes.length).toBe(2);

    const patB = groups.find((g) => g.patientId === "PAT-B");
    expect(patB?.episodes.length).toBe(1);
  });

  it("detects convergence when same patient has multiple active pathways", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-1", patient_id: "PAT-A", cancer_type: "Lung", referral_date: "2026-02-20" })),
      withRisk(makeEpisode({ episode_id: "EP-2", patient_id: "PAT-A", cancer_type: "Breast", referral_date: "2026-02-22" })),
    ];

    const groups = groupByPatient(episodes);
    const patA = groups.find((g) => g.patientId === "PAT-A")!;
    expect(patA.hasConvergenceRisk).toBe(true);
    expect(patA.convergenceNote).toContain("2 active referrals");
  });

  it("flags duplicate cancer type as convergence note", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-1", patient_id: "PAT-A", cancer_type: "Lung", referral_date: "2026-02-20" })),
      withRisk(makeEpisode({ episode_id: "EP-2", patient_id: "PAT-A", cancer_type: "Lung", referral_date: "2026-02-22" })),
    ];

    const groups = groupByPatient(episodes);
    const patA = groups.find((g) => g.patientId === "PAT-A")!;
    expect(patA.hasConvergenceRisk).toBe(true);
    expect(patA.convergenceNote).toContain("possible duplicate");
    expect(patA.convergenceNote).toContain("lung");
  });

  it("does not flag convergence for single-pathway patients", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-1", patient_id: "PAT-A", referral_date: "2026-02-24" })),
    ];

    const groups = groupByPatient(episodes);
    expect(groups[0].hasConvergenceRisk).toBe(false);
    expect(groups[0].convergenceNote).toBeNull();
  });

  it("does not flag convergence when extra pathways are all completed", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({
        episode_id: "EP-1",
        patient_id: "PAT-A",
        status: "active",
        referral_date: "2026-02-24",
      })),
      withRisk(makeEpisode({
        episode_id: "EP-2",
        patient_id: "PAT-A",
        status: "completed",
        referral_date: "2026-01-01",
        milestones: [
          { encounter_id: "E1", date: "2026-01-01", milestone_type: "referral" },
          { encounter_id: "E2", date: "2026-01-08", milestone_type: "first_clinic" },
          { encounter_id: "E3", date: "2026-01-20", milestone_type: "diagnosis" },
          { encounter_id: "E4", date: "2026-02-10", milestone_type: "first_treatment" },
        ],
      })),
    ];

    const groups = groupByPatient(episodes);
    const patA = groups.find((g) => g.patientId === "PAT-A")!;
    expect(patA.hasConvergenceRisk).toBe(false);
  });

  it("sorts groups by worst risk first, convergence second", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-1", patient_id: "PAT-SAFE", referral_date: "2026-02-24" })),
      withRisk(makeEpisode({ episode_id: "EP-2", patient_id: "PAT-URGENT", referral_date: "2026-01-01" })),
      withRisk(makeEpisode({ episode_id: "EP-3", patient_id: "PAT-URGENT", referral_date: "2026-01-05" })),
    ];

    const groups = groupByPatient(episodes);
    expect(groups[0].patientId).toBe("PAT-URGENT");
    expect(groups[1].patientId).toBe("PAT-SAFE");
  });

  it("tracks activeCount correctly", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-1", patient_id: "PAT-A", status: "active", referral_date: "2026-02-24" })),
      withRisk(makeEpisode({
        episode_id: "EP-2",
        patient_id: "PAT-A",
        status: "completed",
        referral_date: "2026-01-01",
        milestones: [
          { encounter_id: "E1", date: "2026-01-01", milestone_type: "referral" },
          { encounter_id: "E2", date: "2026-01-08", milestone_type: "first_clinic" },
          { encounter_id: "E3", date: "2026-01-20", milestone_type: "diagnosis" },
          { encounter_id: "E4", date: "2026-02-10", milestone_type: "first_treatment" },
        ],
      })),
    ];

    const groups = groupByPatient(episodes);
    const patA = groups.find((g) => g.patientId === "PAT-A")!;
    expect(patA.activeCount).toBe(1);
    expect(patA.episodes.length).toBe(2);
  });

  it("handles episodes without patient_id", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({ episode_id: "EP-ORPHAN", patient_id: undefined, referral_date: "2026-02-24" })),
    ];

    const groups = groupByPatient(episodes);
    expect(groups.length).toBe(1);
    expect(groups[0].patientId).toContain("_no_patient_");
  });

  it("detects shared diagnosis encounter as convergence", () => {
    const episodes: EpisodeWithRisk[] = [
      withRisk(makeEpisode({
        episode_id: "EP-1",
        patient_id: "PAT-A",
        cancer_type: "Lung",
        referral_date: "2026-02-01",
        milestones: [
          { encounter_id: "E1", date: "2026-02-01", milestone_type: "referral" },
          { encounter_id: "DIAG-SHARED", date: "2026-02-20", milestone_type: "diagnosis" },
        ],
      })),
      withRisk(makeEpisode({
        episode_id: "EP-2",
        patient_id: "PAT-A",
        cancer_type: "Breast",
        referral_date: "2026-02-05",
        milestones: [
          { encounter_id: "E2", date: "2026-02-05", milestone_type: "referral" },
          { encounter_id: "DIAG-SHARED", date: "2026-02-20", milestone_type: "diagnosis" },
        ],
      })),
    ];

    const groups = groupByPatient(episodes);
    const patA = groups.find((g) => g.patientId === "PAT-A")!;
    expect(patA.hasConvergenceRisk).toBe(true);
    expect(patA.convergenceNote).toContain("share a diagnosis");
  });
});
