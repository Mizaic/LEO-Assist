"use client";

import { useCallback, useId, useState, type ReactNode } from "react";

import { useMotion } from "../motion";

export interface ProgressiveRevealProps {
  summary: string;
  defaultOpen?: boolean;
  children: ReactNode;
}

export function ProgressiveReveal({
  summary,
  defaultOpen = false,
  children,
}: ProgressiveRevealProps) {
  const { reducedMotion } = useMotion();
  const bodyId = useId();
  const [open, setOpen] = useState(defaultOpen);

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  const transitionMs = reducedMotion ? 0 : 180;

  return (
    <div data-testid="progressive-reveal">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={bodyId}
        style={{
          background: "transparent",
          border: "none",
          color: "#1e40af",
          cursor: "pointer",
          padding: "4px 0",
          font: "inherit",
          fontSize: 14,
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        <span aria-hidden="true">{open ? "\u25bc" : "\u25b6"}</span>
        <span>{summary}</span>
      </button>
      <div
        id={bodyId}
        hidden={!open}
        style={{
          marginTop: open ? 8 : 0,
          transition: "margin " + transitionMs + "ms ease-out",
        }}
      >
        {children}
      </div>
    </div>
  );
}
