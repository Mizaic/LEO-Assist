import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PatientGroupList from "../PatientGroupList";
import {
  assessPathwayRisk,
  groupByPatient,
  type Episode,
  type EpisodeWithRisk,
} from "@/lib/pathwayRisk";

const TODAY = "2026-02-26";

function withRisk(ep: Episode): EpisodeWithRisk {
  return { ...ep, risk: assessPathwayRisk(ep, TODAY) };
}

function makeGroups(episodes: Episode[]) {
  return groupByPatient(episodes.map(withRisk));
}

describe("PatientGroupList", () => {
  it("renders patient headers", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-A",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-02-01",
      },
      {
        episode_id: "EP-2",
        patient_id: "PAT-B",
        condition_type: "Breast",
        status: "active",
        referral_date: "2026-02-24",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(screen.getByText("PAT-A")).toBeInTheDocument();
    expect(screen.getByText("PAT-B")).toBeInTheDocument();
  });

  it("shows pathway count per patient", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-A",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-02-20",
      },
      {
        episode_id: "EP-2",
        patient_id: "PAT-A",
        condition_type: "Breast",
        status: "active",
        referral_date: "2026-02-22",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(screen.getByText(/2 pathways/)).toBeInTheDocument();
  });

  it("shows multiple referrals badge for patients with multiple active referrals", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-A",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-02-20",
      },
      {
        episode_id: "EP-2",
        patient_id: "PAT-A",
        condition_type: "Breast",
        status: "active",
        referral_date: "2026-02-22",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(screen.getByText("Multiple referrals")).toBeInTheDocument();
  });

  it("does not show convergence badge for single-pathway patients", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-A",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-02-24",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(screen.queryByText("Multiple referrals")).not.toBeInTheDocument();
  });

  it("auto-expands breached patient groups", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-BREACH",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-01-01",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(screen.getByText("Lung")).toBeInTheDocument();
  });

  it("calls onSelect when a pathway card is clicked", async () => {
    const onSelect = jest.fn();
    const user = userEvent.setup();

    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-BREACH",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-01-01",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={onSelect}
      />,
    );

    await user.click(screen.getByText("Lung"));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ episode_id: "EP-1" }),
    );
  });

  it("expands a collapsed group on header click", async () => {
    const user = userEvent.setup();
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-SAFE",
        condition_type: "Skin",
        status: "active",
        referral_date: "2026-02-24",
      },
    ]);

    const { container } = render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    const collapse = container.querySelector(".MuiCollapse-root");
    expect(collapse).toBeTruthy();
    expect(collapse?.classList.contains("MuiCollapse-hidden")).toBe(true);

    await user.click(screen.getByText("PAT-SAFE"));
    expect(collapse?.classList.contains("MuiCollapse-hidden")).toBe(false);
  });

  it("renders empty state when no groups", () => {
    render(
      <PatientGroupList
        groups={[]}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(
      screen.getByText("No referral pathways match your filters."),
    ).toBeInTheDocument();
  });

  it("renders expand all button", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-SAFE",
        condition_type: "Skin",
        status: "active",
        referral_date: "2026-02-24",
      },
    ]);

    render(
      <PatientGroupList groups={groups} selected={null} onSelect={jest.fn()} />,
    );

    expect(screen.getByLabelText("expand all patients")).toBeInTheDocument();
  });

  it("expands all groups when Expand all is clicked", async () => {
    const user = userEvent.setup();
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-SAFE",
        condition_type: "Skin",
        status: "active",
        referral_date: "2026-02-24",
      },
      {
        episode_id: "EP-2",
        patient_id: "PAT-SAFE2",
        condition_type: "Breast",
        status: "active",
        referral_date: "2026-02-24",
      },
    ]);

    const { container } = render(
      <PatientGroupList groups={groups} selected={null} onSelect={jest.fn()} />,
    );

    await user.click(screen.getByText("Expand all"));
    const collapses = container.querySelectorAll(".MuiCollapse-root");
    collapses.forEach((c) => {
      expect(c.classList.contains("MuiCollapse-hidden")).toBe(false);
    });
  });

  it("collapses all groups when Collapse all is clicked", async () => {
    const user = userEvent.setup();
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-BREACH",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-01-01",
      },
      {
        episode_id: "EP-2",
        patient_id: "PAT-BREACH2",
        condition_type: "Breast",
        status: "active",
        referral_date: "2026-01-01",
      },
    ]);

    render(
      <PatientGroupList groups={groups} selected={null} onSelect={jest.fn()} />,
    );

    // Both breached patients are auto-expanded, so cards are visible
    expect(screen.getByText("Lung")).toBeInTheDocument();
    expect(screen.getByText("Breast")).toBeInTheDocument();
    expect(screen.getByText("Collapse all")).toBeInTheDocument();

    await user.click(screen.getByText("Collapse all"));

    // Button label flips to "Expand all"
    expect(screen.getByText("Expand all")).toBeInTheDocument();
  });

  it("shows convergence note inside expanded group", () => {
    const groups = makeGroups([
      {
        episode_id: "EP-1",
        patient_id: "PAT-DUP",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-01-01",
      },
      {
        episode_id: "EP-2",
        patient_id: "PAT-DUP",
        condition_type: "Lung",
        status: "active",
        referral_date: "2026-01-05",
      },
    ]);

    render(
      <PatientGroupList
        groups={groups}
        selected={null}
        onSelect={jest.fn()}
      />,
    );

    expect(screen.getByText(/possible duplicate/)).toBeInTheDocument();
  });
});
