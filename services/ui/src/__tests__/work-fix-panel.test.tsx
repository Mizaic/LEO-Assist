/**
 * VT-CE7006EE -- live render of the in-context engineer panel.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import WorkFixPanel from "../app/work/WorkFixPanel";
import {
  deployWorkPhrase,
  loadWorkPhrase,
  refreshWorkPhrase,
  saveContextCue,
  savePhraseMapping,
  saveSuppressRule,
  saveTeachExample,
  submitWorkPhrase,
} from "../app/work/workFixApi";
import type { UncodedPhrase } from "../app/work/workFixApi";

jest.mock("../app/work/workFixApi", () => ({
  loadWorkPhrase: jest.fn(),
  refreshWorkPhrase: jest.fn(),
  savePhraseMapping: jest.fn(),
  saveSuppressRule: jest.fn(),
  saveContextCue: jest.fn(),
  saveTeachExample: jest.fn(),
  submitWorkPhrase: jest.fn(),
  deployWorkPhrase: jest.fn(),
}));

jest.mock("@/lib/authContext", () => ({
  useAuth: jest.fn(() => ({
    session: { user: { email: "reviewer@example.com" } },
    status: "authenticated",
  })),
}));

jest.mock("../components/TermSearch", () => ({
  __esModule: true,
  default: ({
    onSelect,
  }: {
    onSelect: (result: { snomed_concept_id: string; term: string }) => void;
  }) => (
    <button
      type="button"
      onClick={() => onSelect({ snomed_concept_id: "123456", term: "Diabetes" })}
    >
      Pick code
    </button>
  ),
}));

const theme = createTheme();

function phraseRow(status: string): UncodedPhrase {
  return {
    phrase_key: "raised hba1c",
    normalized: "raised hba1c",
    extracted_tag: "finding",
    note_count: 1,
    last_score: 0.62,
    last_best_term: "Hemoglobin A1c",
    last_best_concept: "",
    last_best_tag: "finding",
    sample_span: "raised HbA1c",
    sample_sentence: "Raised HbA1c noted.",
    status,
  };
}

function renderPanel() {
  return render(
    <ThemeProvider theme={theme}>
      <WorkFixPanel entityText="raised HbA1c" entityLabel="finding" reviewId="rev-1" />
    </ThemeProvider>,
  );
}

describe("WorkFixPanel live", () => {
  beforeEach(() => {
    jest.mocked(loadWorkPhrase).mockResolvedValue(phraseRow("inbox"));
    jest.mocked(refreshWorkPhrase).mockResolvedValue(phraseRow("draft"));
    jest.mocked(savePhraseMapping).mockResolvedValue(undefined);
    jest.mocked(saveSuppressRule).mockResolvedValue(undefined);
    jest.mocked(saveContextCue).mockResolvedValue(undefined);
    jest.mocked(saveTeachExample).mockResolvedValue(undefined);
    jest.mocked(submitWorkPhrase).mockResolvedValue(undefined);
    jest.mocked(deployWorkPhrase).mockResolvedValue(undefined);
  });

  it("shows when the language model found the phrase", async () => {
    jest.mocked(loadWorkPhrase).mockResolvedValue({
      ...phraseRow("inbox"),
      last_extractor: "llm",
    });
    renderPanel();
    expect(
      await screen.findByText("Found by the language model (LLM)."),
    ).toBeInTheDocument();
  });

  it("shows when named-entity recognition found the phrase", async () => {
    jest.mocked(loadWorkPhrase).mockResolvedValue({
      ...phraseRow("inbox"),
      last_extractor: "model",
    });
    render(
      <ThemeProvider theme={theme}>
        <WorkFixPanel
          entityText="raised HbA1c"
          entityLabel="finding"
          extractionSource="model"
        />
      </ThemeProvider>,
    );
    expect(
      await screen.findByText("Found by named-entity recognition (NER)."),
    ).toBeInTheDocument();
    expect(loadWorkPhrase).toHaveBeenCalledWith(
      expect.objectContaining({
        phrase: "raised HbA1c",
        extractedSource: "model",
      }),
    );
  });

  it("shows debug status without leaving My work", async () => {
    renderPanel();
    expect(screen.getByText("Engineer panel")).toBeInTheDocument();
    expect(await screen.findByText("This phrase is not mapped yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Debug" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fix" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deploy" })).toBeInTheDocument();
  });

  it("does not dump the whole letter into debug", async () => {
    const letter = "Section A Cervix [X] ".repeat(40);
    jest.mocked(loadWorkPhrase).mockResolvedValue({
      ...phraseRow("inbox"),
      sample_sentence: letter,
    });
    render(
      <ThemeProvider theme={theme}>
        <WorkFixPanel
          entityText="Cervix"
          entityLabel="body_structure"
          encounterText={letter}
        />
      </ThemeProvider>,
    );
    expect(await screen.findByText("This phrase is not mapped yet.")).toBeInTheDocument();
    expect(screen.getByText("See the letter on the left.")).toBeInTheDocument();
    expect(screen.queryByText(/Section A Cervix \[X\] Section A/)).not.toBeInTheDocument();
  });

  it("saves a mapping as a draft", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Fix" }));
    await user.click(screen.getByRole("button", { name: "Map this phrase" }));
    await user.click(screen.getByRole("button", { name: "Pick code" }));
    await waitFor(() => {
      expect(savePhraseMapping).toHaveBeenCalledWith(
        "raised HbA1c",
        "123456",
        "Diabetes",
      );
    });
    expect(
      await screen.findByText(/Saved as a draft. Submit it for review next/),
    ).toBeInTheDocument();
  });

  it("saves a do-not-code draft", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Fix" }));
    await user.click(screen.getByRole("button", { name: "Do not code this" }));
    await user.click(screen.getAllByRole("button", { name: "Do not code this" })[1]);
    await waitFor(() => {
      expect(saveSuppressRule).toHaveBeenCalledWith({
        entityText: "raised HbA1c",
        entityLabel: "finding",
        contextPhrase: "",
        reviewId: "rev-1",
      });
    });
  });

  it("saves a context cue that goes live now", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Fix" }));
    await user.click(screen.getByRole("button", { name: "Add a context cue" }));
    await user.click(screen.getByRole("button", { name: "Save cue" }));
    await waitFor(() => {
      expect(saveContextCue).toHaveBeenCalledWith({
        literal: "raised HbA1c",
        category: "NEGATED_EXISTENCE",
        direction: "FORWARD",
      });
    });
    expect(await screen.findByText(/This cue is live now/)).toBeInTheDocument();
  });

  it("saves a missed word and its sentence as a teaching example", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider theme={theme}>
        <WorkFixPanel
          entityText="polyp"
          entityLabel="finding"
          encounterText="Referral for review. Missed polyp noted in clinic."
        />
      </ThemeProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Fix" }));
    await user.click(screen.getByRole("button", { name: "Teach the extractor" }));
    expect(screen.getByText(/Missed polyp noted in clinic/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save teaching example" }));
    await waitFor(() => {
      expect(saveTeachExample).toHaveBeenCalledWith({
        span: "polyp",
        letter: "Referral for review. Missed polyp noted in clinic.",
        semantic_tag: "finding",
        assertion: "present",
      });
    });
    expect(await screen.findByText(/teaching example/i)).toBeInTheDocument();
  });

  it("submits a draft then allows publish by a different person", async () => {
    const user = userEvent.setup();
    jest.mocked(loadWorkPhrase).mockResolvedValue(phraseRow("draft"));
    jest.mocked(refreshWorkPhrase).mockResolvedValue(phraseRow("review"));
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Review" }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));
    await waitFor(() => {
      expect(submitWorkPhrase).toHaveBeenCalledWith("raised HbA1c");
    });
    await user.click(screen.getByRole("button", { name: "Deploy" }));
    await user.click(screen.getByRole("button", { name: "Publish to live" }));
    await waitFor(() => {
      expect(deployWorkPhrase).toHaveBeenCalledWith("raised HbA1c");
    });
  });

  it("disables Publish when the author is the current user", async () => {
    const user = userEvent.setup();
    const { useAuth } = jest.requireMock("@/lib/authContext") as {
      useAuth: jest.Mock;
    };
    useAuth.mockReturnValue({
      session: {
        user: { email: "engineer@example.com" },
        isPlatformAdmin: false,
        organizations: [],
        idleTimeoutMinutes: 30,
        selectedRole: null,
        allowedRoles: [],
        needsRoleChoice: false,
        densityPreference: null,
      },
      status: "authenticated",
      refreshSession: jest.fn(),
    });
    jest.mocked(loadWorkPhrase).mockResolvedValue({
      ...phraseRow("review"),
      draft_author: "engineer@example.com",
    });
    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Deploy" }));
    expect(screen.getByRole("button", { name: "Publish to live" })).toBeDisabled();
    expect(
      screen.getByText(/A different person must publish it/),
    ).toBeInTheDocument();
  });

  it("shows failure kind headline in Debug pane", async () => {
    render(
      <ThemeProvider theme={theme}>
        <WorkFixPanel
          entityText="HbA1c"
          entityLabel="finding"
          failureKind="no_code"
        />
      </ThemeProvider>,
    );
    expect(await screen.findByText("No safe code yet")).toBeInTheDocument();
  });

  it("marks recommended fix button as recommended for no_code", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider theme={theme}>
        <WorkFixPanel
          entityText="HbA1c"
          entityLabel="finding"
          failureKind="no_code"
        />
      </ThemeProvider>,
    );
    await user.click(screen.getByRole("button", { name: "Fix" }));
    expect(
      screen.getByRole("button", { name: "Map this phrase (recommended)" }),
    ).toBeInTheDocument();
  });
});
