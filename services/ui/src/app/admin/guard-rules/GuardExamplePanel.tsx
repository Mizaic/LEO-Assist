/**
 * With / without worked example for a Pipeline Guard.
 *
 * Atlas trace:
 *   Implements: DO-6413D5BC
 *   DI: DI-34712A9A, DI-C5A523A7
 */
"use client";

import { color, elevation, radius, typography } from "@leo/design-system/tokens";

import type { GuardWorkedExample } from "./guardWorkedExamples";

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

export default function GuardExamplePanel({ example }: { example: GuardWorkedExample }) {
  return (
    <div
      data-testid="guard-example-panel"
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
          Same note as the automated test that proves this guard.
        </p>
      </div>
      <NoteCard title="What this does to the data" body={example.dataChange} />
      <NoteCard title="Sample note" body={example.note} italic />
      <div style={{ display: "flex", gap: 12, flex: 1, flexWrap: "wrap" }}>
        <ExampleCard title="Without this guard" body={example.withoutGuard} tone="warn" />
        <ExampleCard title="With this guard" body={example.withGuard} tone="ok" />
      </div>
    </div>
  );
}
