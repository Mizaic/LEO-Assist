// VT-9C2D6F88 live-render path -- per-encounter episode chips with
// confirm-then-unlink (DI-5159A336).
//
// Live React-Testing-Library check that EncounterEpisodeChips
// renders one chip per linked episode, opens a confirm dialog when
// the curator clicks the chip's X, and on confirm calls the
// onUnlink handler with the episode id (which the parent wires to
// detachEncounterFromEpisode without a milestone_type so every
// IS_PART_OF edge between the encounter and the episode is removed
// in one go).

import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import EncounterEpisodeChips from "@/components/mission-control/EncounterEpisodeChips";
import type { EncounterEpisodeLink } from "@/components/mission-control/useMilestoneCuration";

const TWO_LINKS: EncounterEpisodeLink[] = [
  {
    episodeId: "ep-lung",
    episodeLabel: "Lung pathway, ref 14 Jul 25",
    milestoneTypes: ["first_presentation", "referral"],
  },
  {
    episodeId: "ep-bowel",
    episodeLabel: "Bowel pathway, ref 02 Apr 25",
    milestoneTypes: ["primary_care_investigations"],
  },
];

describe("EncounterEpisodeChips - VT-9C2D6F88", () => {
  it("renders one chip per linked episode with the episode label", () => {
    render(<EncounterEpisodeChips episodeLinks={TWO_LINKS} onUnlink={jest.fn()} />);
    const lung = screen.getByTestId("encounter-card-episode-chip-ep-lung");
    const bowel = screen.getByTestId("encounter-card-episode-chip-ep-bowel");
    expect(lung).toHaveTextContent("Lung pathway, ref 14 Jul 25");
    expect(bowel).toHaveTextContent("Bowel pathway, ref 02 Apr 25");
  });

  it("renders nothing when there are no links", () => {
    const { container } = render(
      <EncounterEpisodeChips episodeLinks={[]} onUnlink={jest.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("clicking the chip's X opens a confirm dialog naming the episode and slot count", async () => {
    const user = userEvent.setup();
    render(<EncounterEpisodeChips episodeLinks={TWO_LINKS} onUnlink={jest.fn()} />);
    const chip = screen.getByTestId("encounter-card-episode-chip-ep-lung");
    const deleteButton = chip.querySelector(".MuiChip-deleteIcon") as HTMLElement;
    await user.click(deleteButton);
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Unlink this encounter from the pathway?"
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "Lung pathway, ref 14 Jul 25"
    );
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "2 milestone slots"
    );
  });

  it("Cancel closes the dialog without calling onUnlink", async () => {
    const onUnlink = jest.fn();
    const user = userEvent.setup();
    render(<EncounterEpisodeChips episodeLinks={TWO_LINKS} onUnlink={onUnlink} />);
    const chip = screen.getByTestId("encounter-card-episode-chip-ep-bowel");
    await user.click(chip.querySelector(".MuiChip-deleteIcon") as HTMLElement);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onUnlink).not.toHaveBeenCalled();
  });

  it("Confirm calls onUnlink exactly once with the chosen episode id", async () => {
    const onUnlink = jest.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<EncounterEpisodeChips episodeLinks={TWO_LINKS} onUnlink={onUnlink} />);
    const chip = screen.getByTestId("encounter-card-episode-chip-ep-lung");
    await user.click(chip.querySelector(".MuiChip-deleteIcon") as HTMLElement);
    await user.click(screen.getByRole("button", { name: /^unlink$/i }));
    await waitFor(() => {
      expect(onUnlink).toHaveBeenCalledTimes(1);
      expect(onUnlink).toHaveBeenCalledWith("ep-lung");
    });
  });

  it("surfaces a server failure inline and lets the curator retry instead of crashing (DI-5159A336)", async () => {
    // Regression for the "No IS_PART_OF edge between encounter and
    // episode" runtime overlay: handleConfirm must catch unknown
    // failures and show them in the confirm body so the dialog stays
    // useful. Callers (the chip hook) already swallow 404s for
    // already-detached edges, so anything that reaches here is a real
    // server / network error.
    const onUnlink = jest
      .fn()
      .mockRejectedValueOnce(new Error("Pathway is locked for review"));
    const user = userEvent.setup();
    render(<EncounterEpisodeChips episodeLinks={TWO_LINKS} onUnlink={onUnlink} />);
    const chip = screen.getByTestId("encounter-card-episode-chip-ep-lung");
    await user.click(chip.querySelector(".MuiChip-deleteIcon") as HTMLElement);
    await user.click(screen.getByRole("button", { name: /^unlink$/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toHaveTextContent(
        "Pathway is locked for review"
      );
      expect(
        screen.getByRole("button", { name: /try again/i })
      ).toBeInTheDocument();
    });
  });

  it("single-slot link uses singular wording in the confirm body", async () => {
    const user = userEvent.setup();
    render(<EncounterEpisodeChips episodeLinks={TWO_LINKS} onUnlink={jest.fn()} />);
    const chip = screen.getByTestId("encounter-card-episode-chip-ep-bowel");
    await user.click(chip.querySelector(".MuiChip-deleteIcon") as HTMLElement);
    expect(screen.getByRole("dialog")).toHaveTextContent("1 milestone slot");
    expect(screen.getByRole("dialog")).not.toHaveTextContent(
      "1 milestone slots"
    );
  });
});
