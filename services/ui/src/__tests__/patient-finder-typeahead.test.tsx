/**
 * VT-LEO-AI-230 -- PatientFinder typeahead (live-render layer)
 *
 * Verifies the 250ms debounce on the Search tab so we do not fire a
 * /patient-finder/search call per keystroke.
 */
import "@testing-library/jest-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PatientFinder } from "@/components/sbar-playground/PatientFinder";
import * as analyticsApi from "@/lib/analyticsApi";

jest.mock("@/lib/analyticsApi", () => ({
  __esModule: true,
  searchPatients: jest.fn().mockResolvedValue({ results: [] }),
  patientsByFilter: jest.fn().mockResolvedValue({ results: [] }),
  patientsByCohort: jest.fn().mockResolvedValue({ results: [] }),
  fetchCohorts: jest.fn().mockResolvedValue([]),
  previewCohort: jest
    .fn()
    .mockResolvedValue({ patient_count: 0, sample_patient_ids: [] }),
}));

describe("VT-LEO-AI-230 PatientFinder typeahead debounce", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("debounces typeahead by 250 ms (one search call, not three)", async () => {
    const user = userEvent.setup({
      advanceTimers: jest.advanceTimersByTime,
    });
    render(
      <PatientFinder
        open
        onClose={() => undefined}
        onSelect={() => undefined}
      />,
    );

    const input = await screen.findByTestId("patient-finder-search-input");
    await user.type(input, "smith");

    expect(analyticsApi.searchPatients).not.toHaveBeenCalled();

    jest.advanceTimersByTime(300);
    await Promise.resolve();

    expect(analyticsApi.searchPatients).toHaveBeenCalledTimes(1);
    expect(analyticsApi.searchPatients).toHaveBeenLastCalledWith("smith", 25);
  });
});
