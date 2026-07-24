/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */

/**
 * Covers two fixes reported against the highlight-to-build wizard's
 * "Add a symptom, sign, procedure, or situation" popover:
 *
 *  1. "I select the code and nothing happens" -- multiPick renders
 *     MultiConceptPicker (which lets the reviewer tick more than one
 *     result) instead of ConceptSearchPanel's single-pick flow.
 *  2. "the popover is overflowing [off the bottom of the screen]" --
 *     the popover's paper is observed for resize and repositioned
 *     every time its content grows (results arriving, a ticked
 *     result's "Depth" stepper appearing), not just once on open.
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import ChipSearchPopover from "../ChipSearchPopover";
import { MULTI_CONCEPT_PICKER, SEARCH_PANEL } from "../copy";

function anchorEl(): HTMLElement {
  const el = document.createElement("button");
  document.body.appendChild(el);
  return el;
}

describe("ChipSearchPopover", () => {
  beforeEach(() => {
    (global.fetch as jest.Mock).mockReset();
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => [],
    });
  });

  it("renders ConceptSearchPanel's single-pick search box when multiPick is not set", () => {
    render(
      <ChipSearchPopover
        open
        anchorEl={anchorEl()}
        mode="add"
        focusLabel={null}
        initialQuery=""
        onPick={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    expect(screen.queryByText(MULTI_CONCEPT_PICKER.emptyHint)).not.toBeInTheDocument();
  });

  it("renders MultiConceptPicker's multi-select results list when multiPick is true", () => {
    render(
      <ChipSearchPopover
        open
        anchorEl={anchorEl()}
        mode="add"
        focusLabel={null}
        initialQuery="treatment-resistant dyspepsia"
        multiPick
        onPick={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    expect(screen.getByText(MULTI_CONCEPT_PICKER.emptyHint)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Add \d+ codes?/ }),
    ).toBeInTheDocument();
  });

  it("ignores multiPick outside of add mode -- replace always stays single-pick", () => {
    render(
      <ChipSearchPopover
        open
        anchorEl={anchorEl()}
        mode="replace"
        focusLabel={null}
        initialQuery=""
        multiPick
        onPick={jest.fn()}
        onClose={jest.fn()}
      />,
    );
    expect(screen.queryByText(MULTI_CONCEPT_PICKER.emptyHint)).not.toBeInTheDocument();
  });

  it("picking a code in multi-pick mode confirms and closes the popover", async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => [
        {
          snomed_concept_id: "162031009",
          term: "Indigestion",
          semantic_tag: "finding",
        },
      ],
    });
    const onPick = jest.fn();
    const user = userEvent.setup();
    render(
      <ChipSearchPopover
        open
        anchorEl={anchorEl()}
        mode="add"
        focusLabel={null}
        initialQuery="treatment-resistant dyspepsia"
        multiPick
        onPick={onPick}
        onClose={jest.fn()}
      />,
    );

    await screen.findByText("Indigestion");
    await user.click(screen.getByLabelText("Select Indigestion"));
    await user.click(screen.getByRole("button", { name: "Add 1 code" }));

    expect(onPick).toHaveBeenCalledTimes(1);
    const criterion = onPick.mock.calls[0][0];
    expect(criterion.seeds).toEqual([
      expect.objectContaining({ snomed_concept_id: "162031009" }),
    ]);
  });

  it("observes the popover paper for resize so it can reposition as content grows", () => {
    const observed: Element[] = [];
    const disconnected = jest.fn();
    class FakeResizeObserver {
      observe(el: Element) {
        observed.push(el);
      }
      unobserve() {}
      disconnect() {
        disconnected();
      }
    }
    const originalRO = global.ResizeObserver;
    (global as unknown as { ResizeObserver: unknown }).ResizeObserver =
      FakeResizeObserver;

    try {
      const { unmount } = render(
        <ChipSearchPopover
          open
          anchorEl={anchorEl()}
          mode="add"
          focusLabel={null}
          initialQuery=""
          onPick={jest.fn()}
          onClose={jest.fn()}
        />,
      );

      expect(observed.length).toBeGreaterThan(0);
      // The observed node is the popover's own paper (labelled with
      // its heading), not some inner, already-clipped content box --
      // that's the element whose natural height actually changes as
      // results/depth-steppers appear, and the one MUI needs to
      // reposition against.
      expect(observed[0].getAttribute("aria-label")).toBe(
        SEARCH_PANEL.headings.add,
      );

      act(() => unmount());
      expect(disconnected).toHaveBeenCalled();
    } finally {
      (global as unknown as { ResizeObserver: unknown }).ResizeObserver = originalRO;
    }
  });
});
