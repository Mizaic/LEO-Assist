/**
 * Live-render VT for ReconcilePathwayDrawer.
 *
 * Atlas trace:
 *   DI-9DCC9F84 (Reconcile pathway) -- the drawer is the primary
 *     reviewer surface for in_review pathways.
 *   DI-C424BB44 (VerificationLock primitive) -- this VT proves the
 *     drawer cannot submit without a reviewer notes string and that
 *     the bucket-flip type-to-confirm gate is honoured.
 *   VT-CABCEC8B (reconcile router) -- the drawer is the only caller
 *     of patchEpisodeReconcile in the UI.
 *
 * Acceptance criteria covered:
 *   1. Confirm button is disabled until there is at least one staged
 *      action AND a reviewer notes string.
 *   2. Confirming a slot calls patchEpisodeReconcile with the staged
 *      action, the reviewer email, the reviewer role, and the notes.
 *   3. When the API rejects with a 412 bucket-flip error, the drawer
 *      surfaces BucketFlipWarning and keeps Confirm disabled until
 *      the proposed bucket name is typed.
 *   4. Once the bucket name is typed, a re-submit calls the API with
 *      confirm_bucket_flip: true.
 */

import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

jest.mock("@/lib/missionControlApi", () => {
  const actual = jest.requireActual("@/lib/missionControlApi");
  return {
    ...actual,
    patchEpisodeReconcile: jest.fn(),
  };
});

import ReconcilePathwayDrawer from "@/components/mission-control/ReconcilePathwayDrawer";
import {
  patchEpisodeReconcile,
  type MissionEpisode,
} from "@/lib/missionControlApi";
import type { SlotRowData } from "@/components/mission-control/MilestoneSlotRow";

const EPISODE: MissionEpisode = {
  episode_id: "ep-recon-001",
  cancer_type: "colorectal",
  condition_type: "cancer",
  status: "in_review",
  cancer_stage: null,
  referral_date: "2024-06-15",
  end_date: null,
  diagnostic_interval_days: 35,
  primary_care_interval_days: null,
  inferred_outcome: null,
  auto_close_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  audit_notes: null,
  audit_flag: false,
};

const ROWS: SlotRowData[] = [
  {
    slot: "diagnosis",
    label: "Diagnosis",
    engineEncounterId: "enc-A",
    engineMilestoneType: "diagnosis_made",
    rationale: "First documented colorectal cancer diagnosis.",
    lock: null,
  },
  {
    slot: "first_seen",
    label: "First seen",
    engineEncounterId: "enc-B",
    engineMilestoneType: "first_seen_in_primary_care",
    rationale: "Initial primary care presentation.",
    lock: null,
  },
];

afterEach(() => {
  jest.clearAllMocks();
});

function renderDrawer(overrides: Partial<React.ComponentProps<
  typeof ReconcilePathwayDrawer
>> = {}) {
  const onClose = jest.fn();
  const onSaved = jest.fn();
  const onReplaceClick = jest.fn();
  render(
    <ReconcilePathwayDrawer
      open
      episode={EPISODE}
      rows={ROWS}
      reviewerEmail="reviewer@example.org"
      reviewerRole="clinician"
      locks={null}
      onReplaceClick={onReplaceClick}
      onClose={onClose}
      onSaved={onSaved}
      {...overrides}
    />,
  );
  return { onClose, onSaved, onReplaceClick };
}

describe("ReconcilePathwayDrawer -- confirm flow (DI-9DCC9F84)", () => {
  test("Confirm button is disabled until a slot is staged AND notes are provided", async () => {
    renderDrawer();

    const submit = screen.getByTestId("reconcile-confirm-button");
    expect(submit).toBeDisabled();

    // Stage the diagnosis slot via the Confirm action -- still no notes.
    fireEvent.click(screen.getByTestId("slot-diagnosis-action-confirm"));
    expect(submit).toBeDisabled();

    // Add notes -- now Confirm should enable.
    const notes = screen.getByLabelText(/Reviewer notes/i);
    fireEvent.change(notes, { target: { value: "Engine pick agrees with chart." } });

    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  test("Submitting calls patchEpisodeReconcile with staged action + audit fields", async () => {
    (patchEpisodeReconcile as jest.Mock).mockResolvedValueOnce({
      episode_id: EPISODE.episode_id,
      lifecycle_bucket_before: "in_review",
      lifecycle_bucket_after: "in_review",
      bucket_flipped: false,
      locks: [],
    });
    const { onSaved, onClose } = renderDrawer();

    fireEvent.click(screen.getByTestId("slot-diagnosis-action-confirm"));
    fireEvent.change(screen.getByLabelText(/Reviewer notes/i), {
      target: { value: "Confirmed by reviewer." },
    });

    fireEvent.click(screen.getByTestId("reconcile-confirm-button"));

    await waitFor(() =>
      expect(patchEpisodeReconcile).toHaveBeenCalledWith(
        EPISODE.episode_id,
        expect.objectContaining({
          reviewed_by: "reviewer@example.org",
          reviewer_role: "clinician",
          reason: "Confirmed by reviewer.",
          confirm_bucket_flip: false,
          actions: expect.arrayContaining([
            expect.objectContaining({
              slot: "diagnosis",
              action: "confirm",
              encounter_id: "enc-A",
              milestone_type: "diagnosis_made",
            }),
          ]),
        }),
      ),
    );

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  test("412 bucket flip surfaces the type-to-confirm gate", async () => {
    (patchEpisodeReconcile as jest.Mock).mockRejectedValueOnce(
      new Error("would silently flip the bucket from in_review to confirmed_cancer"),
    );
    renderDrawer();

    fireEvent.click(screen.getByTestId("slot-diagnosis-action-confirm"));
    fireEvent.change(screen.getByLabelText(/Reviewer notes/i), {
      target: { value: "Engine pick is wrong." },
    });

    fireEvent.click(screen.getByTestId("reconcile-confirm-button"));

    // Bucket flip warning appears and the Confirm button stays disabled.
    await waitFor(() =>
      expect(screen.getByTestId("bucket-flip-warning")).toBeInTheDocument(),
    );
    const submit = screen.getByTestId("reconcile-confirm-button");
    expect(submit).toBeDisabled();

    // Type the wrong name -- still disabled.
    const typed = screen.getByTestId("bucket-flip-typed");
    fireEvent.change(typed, { target: { value: "wrong" } });
    expect(submit).toBeDisabled();

    // Type the right name (display form) -- now Confirm enables.
    fireEvent.change(typed, { target: { value: "Confirmed cancer" } });
    await waitFor(() => expect(submit).not.toBeDisabled());
  });

  test("After typing the bucket name, re-submit sends confirm_bucket_flip: true", async () => {
    (patchEpisodeReconcile as jest.Mock).mockRejectedValueOnce(
      new Error("would silently flip the bucket from in_review to confirmed_cancer"),
    );
    (patchEpisodeReconcile as jest.Mock).mockResolvedValueOnce({
      episode_id: EPISODE.episode_id,
      lifecycle_bucket_before: "in_review",
      lifecycle_bucket_after: "confirmed_cancer",
      bucket_flipped: true,
      locks: [],
    });
    renderDrawer();

    fireEvent.click(screen.getByTestId("slot-diagnosis-action-confirm"));
    fireEvent.change(screen.getByLabelText(/Reviewer notes/i), {
      target: { value: "Need to flip bucket." },
    });

    fireEvent.click(screen.getByTestId("reconcile-confirm-button"));
    await waitFor(() =>
      expect(screen.getByTestId("bucket-flip-warning")).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByTestId("bucket-flip-typed"), {
      target: { value: "confirmed_cancer" },
    });
    const submit = screen.getByTestId("reconcile-confirm-button");
    await waitFor(() => expect(submit).not.toBeDisabled());

    fireEvent.click(submit);

    await waitFor(() => expect(patchEpisodeReconcile).toHaveBeenCalledTimes(2));
    const secondCall = (patchEpisodeReconcile as jest.Mock).mock.calls[1];
    expect(secondCall[1]).toEqual(
      expect.objectContaining({ confirm_bucket_flip: true }),
    );
  });
});
