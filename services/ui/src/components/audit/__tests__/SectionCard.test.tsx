import React from "react";
import { render, screen } from "@testing-library/react";
import SectionCard from "../SectionCard";

describe("SectionCard", () => {
  it("renders title and description", () => {
    render(
      <SectionCard id="test-section" title="Cancer Type" description="Distribution of cancer types.">
        <div>Content</div>
      </SectionCard>,
    );
    expect(screen.getByText("Cancer Type")).toBeInTheDocument();
    expect(screen.getByText("Distribution of cancer types.")).toBeInTheDocument();
  });

  it("renders children", () => {
    render(
      <SectionCard id="test" title="Test">
        <span data-testid="child">hello</span>
      </SectionCard>,
    );
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  it("shows skeleton when loading", () => {
    render(
      <SectionCard id="test" title="Test" loading>
        <div>should not render</div>
      </SectionCard>,
    );
    expect(screen.queryByText("should not render")).not.toBeInTheDocument();
  });

  it("shows error alert when error is set", () => {
    render(
      <SectionCard id="test" title="Test" error="Data unavailable">
        <div>Content</div>
      </SectionCard>,
    );
    expect(screen.getByText("Data unavailable")).toBeInTheDocument();
  });

  it("shows pipeline_pending chip", () => {
    render(
      <SectionCard id="test" title="Test" availability="pipeline_pending">
        <div />
      </SectionCard>,
    );
    expect(screen.getByText(/Extraction in progress/)).toBeInTheDocument();
  });

  it("shows manual_entry chip and alert", () => {
    render(
      <SectionCard id="test" title="Test" availability="manual_entry">
        <div />
      </SectionCard>,
    );
    expect(screen.getByText(/Requires data entry/)).toBeInTheDocument();
    expect(screen.getByText(/structured data entry/i)).toBeInTheDocument();
  });

  it("shows external_feed chip and alert", () => {
    render(
      <SectionCard id="test" title="Test" availability="external_feed">
        <div />
      </SectionCard>,
    );
    expect(screen.getByText(/Requires external feed/)).toBeInTheDocument();
  });
});
