import React from "react";
import { render, screen } from "@testing-library/react";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import PatientCaseRow, {
  getDisplayEpisodes,
  getEpisodeDisplayInterval,
  summarizeEpisodeReviews,
} from "@/components/mission-control/PatientCaseRow";
import type { MissionEpisode, MissionPatient } from "@/lib/missionControlApi";

function valueOrDefault<K extends keyof MissionEpisode>(
  source: Partial<MissionEpisode>,
  key: K,
  fallback: MissionEpisode[K]
): MissionEpisode[K] {
  return Object.prototype.hasOwnProperty.call(source, key)
    ? (source[key] as MissionEpisode[K])
    : fallback;
}

function episode(overrides: Partial<MissionEpisode> = {}): MissionEpisode {
  return {
    episode_id: overrides.episode_id ?? "ep-1",
    cancer_type: overrides.cancer_type ?? "breast",
    condition_type: overrides.condition_type ?? "cancer",
    status: overrides.status ?? "completed",
    cancer_stage: overrides.cancer_stage ?? null,
    referral_date: valueOrDefault(overrides, "referral_date", "2025-01-01"),
    end_date: overrides.end_date ?? null,
    specialist_visit_date: overrides.specialist_visit_date ?? null,
    diagnostic_interval_days: overrides.diagnostic_interval_days ?? null,
    benign_interval_days: overrides.benign_interval_days ?? null,
    primary_care_interval_days: overrides.primary_care_interval_days ?? null,
    inferred_outcome: overrides.inferred_outcome ?? null,
    auto_close_reason: overrides.auto_close_reason ?? null,
    reviewed_by: overrides.reviewed_by ?? null,
    reviewed_at: overrides.reviewed_at ?? null,
    review_verdict: overrides.review_verdict ?? null,
    audit_notes: overrides.audit_notes ?? null,
    audit_flag: overrides.audit_flag ?? false,
    linked_encounter_ids: overrides.linked_encounter_ids ?? [],
    milestones: overrides.milestones ?? [],
  };
}

function patient(episodes: MissionEpisode[]): MissionPatient {
  return {
    patient_id: "P-001",
    age: 60,
    gender: "female",
    practice_name: "Test Practice",
    episodes,
  };
}

function renderRow(episodes: MissionEpisode[]) {
  render(
    <Table>
      <TableBody>
        <PatientCaseRow patient={patient(episodes)} onOpen={jest.fn()} />
      </TableBody>
    </Table>
  );
}

describe("PatientCaseRow episode interval display", () => {
  test("shows a confirmed episode status and diagnostic interval", () => {
    renderRow([
      episode({
        status: "completed",
        cancer_type: "breast",
        diagnostic_interval_days: 37,
        reviewed_by: "qa@example.com",
      }),
    ]);

    expect(screen.getByLabelText("Confirmed cancer")).toBeInTheDocument();
    expect(screen.getByText("Breast")).toBeInTheDocument();
    expect(screen.getByLabelText("Time to diagnosis: 37 days")).toBeInTheDocument();
    expect(screen.getByText("Reviewed")).toBeInTheDocument();
  });

  test("shows a cancer-excluded episode interval when no diagnosis exists", () => {
    renderRow([
      episode({
        status: "closed_benign",
        cancer_type: "lung",
        diagnostic_interval_days: null,
        benign_interval_days: 29,
        reviewed_by: "qa@example.com",
      }),
    ]);

    expect(screen.getByLabelText("No cancer found")).toBeInTheDocument();
    expect(screen.getByText("Lung")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Time to cancer excluded: 29 days")
    ).toBeInTheDocument();
  });

  test("shows every pathway for a multi-episode patient", () => {
    renderRow([
      episode({
        episode_id: "ep-upper",
        status: "active",
        cancer_type: "upper_gi",
        referral_date: "2025-06-17",
      }),
      episode({
        episode_id: "ep-lung",
        status: "closed_benign",
        cancer_type: "lung",
        referral_date: "2025-06-17",
        benign_interval_days: 29,
        reviewed_by: "qa@example.com",
      }),
      episode({
        episode_id: "ep-breast",
        status: "completed",
        cancer_type: "breast",
        referral_date: "2025-08-12",
        diagnostic_interval_days: 37,
        reviewed_by: "qa@example.com",
      }),
    ]);

    expect(screen.getByText("3 pathways")).toBeInTheDocument();
    expect(screen.getByText("Upper gut")).toBeInTheDocument();
    expect(screen.getByText("Lung")).toBeInTheDocument();
    expect(screen.getByText("Breast")).toBeInTheDocument();
    expect(
      screen.getByLabelText("Time to cancer excluded: 29 days")
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Time to diagnosis: 37 days")).toBeInTheDocument();
    expect(screen.getByText("2/3 reviewed")).toBeInTheDocument();
  });

  test("helper functions choose intervals, reviews, and deterministic order", () => {
    const episodes = [
      episode({ episode_id: "later", referral_date: "2025-08-12" }),
      episode({
        episode_id: "benign",
        status: "closed_benign",
        referral_date: "2025-06-17",
        benign_interval_days: 29,
        reviewed_by: "qa@example.com",
      }),
    ];
    const ordered = getDisplayEpisodes(patient(episodes));

    expect(ordered.map((item) => item.episode_id)).toEqual(["benign", "later"]);
    expect(getEpisodeDisplayInterval(ordered[0])).toEqual({
      days: 29,
      label: "Time to cancer excluded",
    });
    expect(summarizeEpisodeReviews(ordered)).toBe("1/2 reviewed");
  });

  test("derives cancer-excluded interval from end_date when benign_closure milestone is absent (matches EpisodeTimeline)", () => {
    const ep = episode({
      status: "closed_benign",
      referral_date: "2024-04-30",
      end_date: "2024-07-03",
      benign_interval_days: null,
      milestones: [
        { milestone_type: "first_presentation", encounter_id: "e-1", date: "2024-04-30" },
        { milestone_type: "referral", encounter_id: "e-1", date: "2024-04-30" },
        { milestone_type: "first_seen", encounter_id: "e-2", date: "2024-05-06" },
      ],
    });
    expect(getEpisodeDisplayInterval(ep)).toEqual({
      days: 64,
      label: "Time to cancer excluded",
    });
  });

  test("uses first presentation as the referral anchor when referral date is missing", () => {
    const inferred = episode({
      referral_date: null,
      diagnostic_interval_days: null,
      benign_interval_days: null,
      milestones: [
        {
          milestone_type: "first_presentation",
          encounter_id: "e-1",
          date: "2025-01-10",
        },
        {
          milestone_type: "diagnosis_confirmed",
          encounter_id: "e-2",
          date: "2025-02-14",
        },
      ],
    });

    expect(getEpisodeDisplayInterval(inferred)).toEqual({
      days: 35,
      label: "Time to diagnosis",
    });

    renderRow([inferred]);
    expect(screen.getByText("10 Jan 25")).toBeInTheDocument();
    expect(screen.getByLabelText("Time to diagnosis: 35 days")).toBeInTheDocument();
  });
});
