/**
 * Atlas trace:
 *   DO: DO-5D885390
 *   DI: DI-693FFEEA
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { color, typography } from "@leo/design-system/tokens";

import {
  EditorAccordionBody,
  EditorAccordionHeader,
  useEditorStripStyle,
} from "./EditorStrip";

export interface ValidationWarning {
  severity: "error" | "warning" | "info";
  message: string;
}

export function ValidationPanel({ warnings }: { warnings: ValidationWarning[] }) {
  const [open, setOpen] = useState(false);
  const strip = useEditorStripStyle();
  const errorCount = warnings.filter((w) => w.severity === "error").length;
  const warnCount = warnings.filter((w) => w.severity === "warning").length;
  const allGood = errorCount === 0 && warnCount === 0;
  return (
    <div style={strip} data-testid="pathway-validation-strip">
      <EditorAccordionHeader
        title="Pipeline validation"
        open={open}
        onToggle={() => setOpen((v) => !v)}
        icon={
          allGood ? (
            <CheckCircleOutlineIcon fontSize="small" sx={{ color: color.status.success }} />
          ) : (
            <WarningAmberIcon
              fontSize="small"
              sx={{ color: errorCount > 0 ? color.status.danger : color.status.warning }}
            />
          )
        }
        trailing={<ValidationBadges errorCount={errorCount} warnCount={warnCount} allGood={allGood} />}
      />
      <EditorAccordionBody open={open}>
        <Stack spacing={0.5}>
          {warnings.map((w, i) => (
            <Alert
              key={i}
              severity={w.severity}
              sx={{ py: 0, fontSize: "0.78rem", "& .MuiAlert-message": { py: 0.5 } }}
            >
              {w.message}
            </Alert>
          ))}
        </Stack>
      </EditorAccordionBody>
    </div>
  );
}

function ValidationBadges({
  errorCount,
  warnCount,
  allGood,
}: {
  errorCount: number;
  warnCount: number;
  allGood: boolean;
}) {
  if (allGood) {
    return <ToneBadge label="Valid" fg={color.status.success} />;
  }
  return (
    <span style={{ display: "inline-flex", gap: 6 }}>
      {errorCount > 0 ? (
        <ToneBadge
          label={errorCount + " error" + (errorCount > 1 ? "s" : "")}
          fg={color.status.danger}
        />
      ) : null}
      {warnCount > 0 ? (
        <ToneBadge
          label={warnCount + " warning" + (warnCount > 1 ? "s" : "")}
          fg={color.status.warning}
        />
      ) : null}
    </span>
  );
}

function ToneBadge({ label, fg }: { label: string; fg: string }) {
  return (
    <span
      style={{
        height: 22,
        padding: "0 8px",
        borderRadius: 999,
        border: "1px solid " + color.text.secondary,
        background: color.surface.alt,
        color: fg,
        fontSize: 11,
        fontWeight: 700,
        display: "inline-flex",
        alignItems: "center",
        fontFamily: typography.fontFamily.body,
      }}
    >
      {label}
    </span>
  );
}
