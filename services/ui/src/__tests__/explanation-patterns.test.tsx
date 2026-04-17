/**
 * VT-LEO-AI-116 - Explanation pattern primitives and readability gate.
 */

import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import PageIntro from "@/components/ui/PageIntro";
import HelpPopover from "@/components/ui/HelpPopover";
import ProgressiveReveal from "@/components/ui/ProgressiveReveal";
import GlossaryTerm from "@/components/ui/GlossaryTerm";
import { GLOSSARY } from "@/lib/glossary";
import { fleschKincaidGrade } from "@/lib/readability";

describe("VT-LEO-AI-116 explanation patterns", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test("TC-001 PageIntro renders why/how/what and persists collapse state", () => {
    render(
      <PageIntro
        screenId="test-screen"
        why="Why you are here"
        how="How to complete this"
        what="What happens next"
      />,
    );
    expect(screen.getByText("Why you are here")).toBeInTheDocument();
    expect(screen.getByText(/How to complete this/)).toBeInTheDocument();
    expect(screen.getAllByText(/What happens next/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /hide details/i }));
    expect(window.localStorage.getItem("leo-pageintro-test-screen")).toBe(
      "collapsed",
    );
  });

  test("TC-002 HelpPopover trigger opens a labelled dialog", () => {
    render(<HelpPopover title="Assertion" body="How the record treats this." />);
    fireEvent.click(screen.getByRole("button", { name: /what is this/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    const labelId = dialog.getAttribute("aria-labelledby");
    expect(labelId).toBeTruthy();
    expect(document.getElementById(labelId as string)?.textContent).toBe(
      "Assertion",
    );
  });

  test("TC-004 ProgressiveReveal toggles aria-expanded and body visibility", () => {
    render(
      <ProgressiveReveal summary="More options">
        <div>Advanced knob</div>
      </ProgressiveReveal>,
    );
    const trigger = screen.getByRole("button", { name: /more options/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Advanced knob")).toBeInTheDocument();
  });

  test("TC-005 GlossaryTerm opens a plain-language popover with glossary body", () => {
    render(<GlossaryTerm termId="haematuria">haematuria</GlossaryTerm>);
    fireEvent.click(screen.getByRole("button", { name: /what is haematuria/i }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toBeInTheDocument();
    expect(dialog.textContent).toMatch(/blood/i);
  });

  test("TC-005b GlossaryTerm with unknown termId renders children only", () => {
    render(<GlossaryTerm termId="does-not-exist">raw text</GlossaryTerm>);
    expect(screen.getByText("raw text")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("TC-006 every glossary plainLanguage string has FK grade <= 9", () => {
    const failures = Object.values(GLOSSARY)
      .map((entry) => ({
        termId: entry.termId,
        grade: fleschKincaidGrade(entry.plainLanguage),
      }))
      .filter((item) => item.grade > 9);
    expect(failures).toEqual([]);
  });
});
