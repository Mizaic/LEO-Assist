/**
 * VT-LEO-AI-115 TC-005 - StatusDot encodes status through shape and
 * accessible label as well as colour.
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { StatusDot } from "@/components/ui/StatusDot";

describe("StatusDot non-colour encoding", () => {
  test("renders data-shape that differs between statuses", () => {
    const { container: healthyContainer } = render(
      <StatusDot status="healthy" reason="Within range" />,
    );
    const healthy = healthyContainer.querySelector("[data-shape]");
    const healthyShape = healthy?.getAttribute("data-shape");
    expect(healthyShape).toBeTruthy();

    const { container: errorContainer } = render(
      <StatusDot status="error" reason="Out of range" />,
    );
    const errorShape = errorContainer
      .querySelector("[data-shape]")
      ?.getAttribute("data-shape");
    expect(errorShape).toBeTruthy();
    expect(errorShape).not.toBe(healthyShape);
  });

  test("aria-label includes the status word", () => {
    render(<StatusDot status="warning" reason="Borderline result" />);
    const role = screen.getAllByRole("img");
    const withLabel = role.find((node) =>
      (node.getAttribute("aria-label") ?? "").toLowerCase().includes("warning"),
    );
    expect(withLabel).toBeTruthy();
  });
});
