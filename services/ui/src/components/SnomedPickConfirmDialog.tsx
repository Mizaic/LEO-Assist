/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { ReactNode } from "react";
import { color, typography } from "@leo/design-system/tokens";

import ConfirmDialog from "@/components/ConfirmDialog";

export function SnomedPickConfirmDialog({
  copy,
  pick,
  contextRows,
  action,
  children,
}: {
  copy: { title: string; lead: string; confirmLabel: string };
  pick: { term: string; conceptId: string; tag?: string };
  contextRows?: { label: string; value: string }[];
  action: { busy?: boolean; onConfirm: () => void; onCancel: () => void };
  children?: ReactNode;
}) {
  return (
    <ConfirmDialog
      title={copy.title}
      body={copy.lead}
      confirmLabel={copy.confirmLabel}
      busy={action.busy}
      maxWidth="sm"
      onConfirm={action.onConfirm}
      onCancel={action.onCancel}
    >
      <PickPreview pick={pick} rows={contextRows} />
      {children}
    </ConfirmDialog>
  );
}

function PickPreview({
  pick,
  rows,
}: {
  pick: { term: string; conceptId: string; tag?: string };
  rows?: { label: string; value: string }[];
}) {
  const meta = pick.tag ? pick.conceptId + " · " + pick.tag : pick.conceptId;
  return (
    <div data-testid="snomed-pick-confirm" style={previewStyle()}>
      {rows?.map((row) => (
        <PreviewRow key={row.label} label={row.label} value={row.value} />
      ))}
      <div style={{ fontWeight: 700, color: color.text.primary }}>{pick.term}</div>
      <div style={{ marginTop: 4, fontSize: 13, color: color.text.secondary }}>{meta}</div>
    </div>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: typography.letterSpacing.caption,
          textTransform: "uppercase",
          color: color.text.caption,
        }}
      >
        {label}
      </div>
      <div style={{ marginTop: 2, color: color.text.primary }}>{value}</div>
    </div>
  );
}

function previewStyle() {
  return {
    marginTop: 14,
    padding: "12px 14px",
    borderRadius: 12,
    border: "1px solid " + color.brand.primary,
    background: color.surface.alt,
    fontFamily: typography.fontFamily.body,
  };
}
