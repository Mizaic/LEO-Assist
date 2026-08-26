/**
 * VT-1215D85D / DI-B00BD595 -- emergency override on phrase publish.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import PhrasePublishDialog from "../app/work/PhrasePublishDialog";
import {
  fetchPhraseItem,
  publishPhrase,
} from "../app/settings/surface-forms/phraseMappingsApi";

jest.mock("../app/settings/surface-forms/phraseMappingsApi", () => ({
  fetchPhraseItem: jest.fn(),
  publishPhrase: jest.fn(),
  sendBackPhrase: jest.fn(),
}));

jest.mock("@/lib/authContext", () => ({
  useAuth: jest.fn(),
}));

const theme = createTheme();

function phrase() {
  return {
    phrase_key: "psa",
    normalized: "psa",
    extracted_tag: "procedure",
    note_count: 1,
    last_score: 0.8,
    last_best_term: "PSA",
    last_best_concept: "",
    last_best_tag: "procedure",
    sample_span: "PSA",
    sample_sentence: "PSA is raised.",
    status: "review",
    draft_action: "map",
    draft_concept_term: "Prostate specific antigen level",
    draft_author: "admin@example.com",
  };
}

function session(isPlatformAdmin: boolean) {
  return {
    user: { email: "admin@example.com" },
    isPlatformAdmin,
    organizations: [],
    idleTimeoutMinutes: 30,
    selectedRole: null,
    allowedRoles: [],
    needsRoleChoice: false,
    densityPreference: null,
  };
}

function renderDialog() {
  return render(
    <ThemeProvider theme={theme}>
      <PhrasePublishDialog
        task={{
          task_id: "phrase_publish:psa",
          task_type: "phrase_publish",
          severity: 1,
          summary: "Map PSA",
          age_days: 0,
          resolve_url: "/work",
          draft_author: "admin@example.com",
        }}
        onClose={jest.fn()}
        onResolved={jest.fn()}
      />
    </ThemeProvider>,
  );
}

describe("Phrase publish emergency override", () => {
  beforeEach(() => {
    jest.mocked(fetchPhraseItem).mockResolvedValue(phrase());
    jest.mocked(publishPhrase).mockResolvedValue({});
  });

  it("hides the emergency path when the author is not a platform admin", async () => {
    const { useAuth } = jest.requireMock("@/lib/authContext") as {
      useAuth: jest.Mock;
    };
    useAuth.mockReturnValue({ session: session(false), status: "authenticated" });
    renderDialog();
    expect(
      await screen.findByText(/A different person must publish it/),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/Why do you need this emergency override/),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to live" })).toBeDisabled();
  });

  it("sends the reason when a platform admin author confirms", async () => {
    const user = userEvent.setup();
    const { useAuth } = jest.requireMock("@/lib/authContext") as {
      useAuth: jest.Mock;
    };
    useAuth.mockReturnValue({ session: session(true), status: "authenticated" });
    renderDialog();
    const reason = await screen.findByLabelText(
      /Why do you need this emergency override/,
    );
    await user.type(reason, "No second reviewer on duty tonight");
    await user.click(screen.getByRole("button", { name: "Publish to live" }));
    await waitFor(() => {
      expect(publishPhrase).toHaveBeenCalledWith(
        "psa",
        "No second reviewer on duty tonight",
      );
    });
  });
});
