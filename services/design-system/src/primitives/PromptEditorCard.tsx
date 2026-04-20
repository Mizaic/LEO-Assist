/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-124AC2C4
 *   DI: DI-613A48DA
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-124AC2C4")
 */
"use client";

/**
 * PromptEditorCard -- a focused chrome primitive for the AI Instructions
 * editor (Wave E Phase 4b / DI-LEO-AI-170 / VT-LEO-AI-169).
 *
 * Exposes:
 *   - title + optional version chip
 *   - a primary action slot (Save) and an optional secondary action (AI improve)
 *   - a tabs slot
 *   - a body slot
 *
 * Built on plain HTML so the card composes inside both Knowledge and
 * Pathway routes regardless of the upstream MUI theme. The orchestrator
 * passes its existing tab/body content as children; PromptEditorCard owns
 * only the chrome.
 */

import { type ReactNode } from "react";

import { useMotion } from "../motion";

export interface PromptEditorCardProps {
  title: string;
  subtitle?: string;
  versionLabel?: string | null;
  primaryAction?: ReactNode;
  secondaryAction?: ReactNode;
  tabs?: ReactNode;
  children: ReactNode;
  /** Optional id used for the title element so consumers can wire aria-labelledby. */
  id?: string;
}

export function PromptEditorCard({
  title,
  subtitle,
  versionLabel,
  primaryAction,
  secondaryAction,
  tabs,
  children,
  id,
}: PromptEditorCardProps) {
  const { reducedMotion } = useMotion();
  const titleId = id ? id + "-title" : undefined;
  const transitionMs = reducedMotion ? 0 : 180;

  return (
    <section
      aria-labelledby={titleId}
      data-testid="prompt-editor-card"
      style={{
        background: "var(--mui-palette-background-paper, #ffffff)",
        border: "1px solid rgba(15, 23, 42, 0.08)",
        borderRadius: 12,
        padding: "16px 20px",
        marginBottom: 16,
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: subtitle || versionLabel ? 4 : 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <h2
            id={titleId}
            style={{
              margin: 0,
              fontSize: 18,
              fontWeight: 700,
              lineHeight: 1.3,
            }}
          >
            {title}
          </h2>
          {subtitle ? (
            <p
              style={{
                margin: "2px 0 0 0",
                fontSize: 13,
                color: "rgba(15, 23, 42, 0.64)",
              }}
            >
              {subtitle}
            </p>
          ) : null}
        </div>
        {versionLabel ? (
          <span
            style={{
              border: "1px solid rgba(15, 23, 42, 0.16)",
              padding: "2px 10px",
              borderRadius: 999,
              fontSize: 12,
              color: "rgba(15, 23, 42, 0.72)",
            }}
            aria-label={"Version " + versionLabel}
          >
            {versionLabel}
          </span>
        ) : null}
        {secondaryAction}
        {primaryAction}
      </header>

      {tabs ? (
        <div
          style={{
            borderBottom: "1px solid rgba(15, 23, 42, 0.08)",
            marginBottom: 12,
            transition: "margin " + transitionMs + "ms ease-out",
          }}
        >
          {tabs}
        </div>
      ) : null}

      <div>{children}</div>
    </section>
  );
}
