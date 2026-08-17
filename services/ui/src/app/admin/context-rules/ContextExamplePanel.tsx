/**
 * With / without worked example for a Context Rule category.
 *
 * Atlas trace:
 *   Implements: DO-CFA1ED55
 *   DI: DI-340279C1, DI-C5A523A7
 */
"use client";

import { color, elevation, radius, typography } from "@leo/design-system/tokens";

import type { ContextWorkedExample } from "./types";

function ExampleCard({
  title,
  body,
  tone,
}: {
  title: string;
  body: string;
  tone: "warn" | "ok";
}) {
  const ok = tone === "ok";
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        padding: 14,
        borderRadius: radius.md,
        boxShadow: elevation.card,
        background: ok ? "rgba(4, 120, 87, 0.1)" : "rgba(185, 28, 28, 0.08)",
        color: ok ? color.status.success : color.status.danger,
      }}
    >
      <strong
        style={{
          display: "block",
          marginBottom: 6,
          fontSize: 12,
          letterSpacing: typography.letterSpacing.caption,
          textTransform: "uppercase",
        }}
      >
        {title}
      </strong>
      <span style={{ display: "block", fontSize: 14, fontWeight: 400 }}>{body}</span>
    </div>
  );
}

function NoteCard({ title, body, italic }: { title: string; body: string; italic?: boolean }) {
  return (
    <div
      style={{
        padding: 14,
        borderRadius: radius.md,
        background: color.surface.raised,
        boxShadow: elevation.card,
      }}
    >
      <strong
        style={{
          display: "block",
          marginBottom: 6,
          fontSize: 12,
          letterSpacing: typography.letterSpacing.caption,
          textTransform: "uppercase",
          color: color.text.secondary,
        }}
      >
        {title}
      </strong>
      <p
        style={{
          margin: 0,
          fontSize: 14,
          color: color.text.primary,
          fontStyle: italic ? "italic" : "normal",
          fontFamily: typography.fontFamily.body,
        }}
      >
        {body}
      </p>
    </div>
  );
}

export default function ContextExamplePanel({ example }: { example: ContextWorkedExample }) {
  return (
    <div
      data-testid="context-example-panel"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 14,
        height: "100%",
        fontFamily: typography.fontFamily.body,
      }}
    >
      <div>
        <h3
          style={{
            margin: 0,
            fontFamily: typography.fontFamily.heading,
            fontSize: 16,
            fontWeight: 700,
            letterSpacing: typography.letterSpacing.display,
            color: color.text.primary,
          }}
        >
          Worked example
        </h3>
        <p style={{ margin: "4px 0 0", fontSize: 14, color: color.text.secondary }}>
          Same category story. The sample note follows the phrase you pick.
        </p>
      </div>
      <NoteCard title="What this does to the data" body={example.dataChange} />
      <NoteCard title="Sample note" body={example.note} italic />
      <div style={{ display: "flex", gap: 12, flex: 1, flexWrap: "wrap" }}>
        <ExampleCard title="Without this rule" body={example.withoutGuard} tone="warn" />
        <ExampleCard title="With this rule" body={example.withGuard} tone="ok" />
      </div>
    </div>
  );
}
