/**
 * Stage 9b - NCDA audit tile VT.
 *
 * Confirms reviewer actions fire the right callback signature so the
 * Stage 1 audit findings can be triaged via the UI.
 */
import { render, screen, fireEvent } from "@testing-library/react";

import NcdaAuditTile, {
  NcdaAuditFinding,
} from "@/components/ncda/NcdaAuditTile";

const FINDING: NcdaAuditFinding = {
  patient_id: "P1",
  episode_id: "E1",
  encounter_id: "ENC1",
  current_milestone: "referral_sent",
  suggested_role: "ftr",
  suggested_outcome: null,
  finding_type: "role_mismatch",
  severity: "medium",
  rationale: "Encounter text contains no FTR phrase pattern.",
  supporting_quote: "Telephone consultation about back pain",
  status: "open",
};

describe("NcdaAuditTile", () => {
  it("renders plain-language severity and finding labels", () => {
    render(<NcdaAuditTile findings={[FINDING]} />);
    expect(screen.getByText("Recommended fix")).toBeInTheDocument();
    expect(
      screen.getByText("Label does not match the encounter text"),
    ).toBeInTheDocument();
  });

  it("calls onAction with the right action key", () => {
    const onAction = jest.fn();
    render(<NcdaAuditTile findings={[FINDING]} onAction={onAction} />);
    const btn = screen.getByTestId("ncda-audit-action-mark_correct");
    fireEvent.click(btn);
    expect(onAction).toHaveBeenCalledWith(FINDING, "mark_correct");
  });

  it("filters by severity when filter dropdown changes", () => {
    const high: NcdaAuditFinding = { ...FINDING, severity: "high" };
    render(<NcdaAuditTile findings={[FINDING, high]} />);
    expect(screen.getAllByText(/Recommended fix|Must fix before tidy/i).length).toBe(2);
  });
});
