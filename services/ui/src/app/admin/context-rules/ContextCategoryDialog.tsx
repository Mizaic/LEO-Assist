/**
 * Category detail dialog -- landscape 16:9.
 * Left: exact phrases. Right: with / without example.
 *
 * Atlas trace:
 *   Implements: DO-CFA1ED55
 *   DI: DI-340279C1, DI-C5A523A7
 */
"use client";

import { useId } from "react";
import { motion as fm } from "framer-motion";
import {
  frostStyle,
  SpringSwap,
  springOrInstant,
  springs,
  tapScale,
  useMotion,
  useReducedTransparency,
} from "@leo/design-system";
import { color, elevation, radius, typography } from "@leo/design-system/tokens";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";

import ContextExamplePanel from "./ContextExamplePanel";
import { ContextDialogTitleBar } from "./ContextDialogTitleBar";
import { ContextPhraseRow } from "./ContextPhraseRow";
import type { CategoryCopy } from "./categoryCopy";
import { directionLabel, resolveContextExample, scopeLabel } from "./categoryCopy";
import type { ContextRule } from "./types";

interface ContextCategoryDialogProps {
  copy: CategoryCopy;
  rules: ContextRule[];
  selectedRule: ContextRule | null;
  onSelect: (rule: ContextRule) => void;
  onClose: () => void;
  onDeactivate: (rule: ContextRule) => void;
}

function CategoryDocs({ copy }: { copy: CategoryCopy }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, fontSize: 14 }}>
      <p style={{ margin: 0, color: color.text.primary }}>
        <strong>What it does. </strong>
        {copy.what}
      </p>
      <p style={{ margin: 0, color: color.text.primary }}>
        <strong>Why it is needed. </strong>
        {copy.why}
      </p>
      <p style={{ margin: 0, color: color.text.primary }}>
        <strong>If it is wrong. </strong>
        {copy.ifWrong}
      </p>
    </div>
  );
}

function SelectedRuleDetail({
  rule,
  onDeactivate,
}: {
  rule: ContextRule;
  onDeactivate: (rule: ContextRule) => void;
}) {
  const { reducedMotion } = useMotion();
  const canDeactivate = rule.source === "custom" && rule.active && rule.rule_id;
  return (
    <div
      style={{
        padding: 14,
        borderRadius: radius.md,
        background: color.surface.raised,
        boxShadow: elevation.card,
      }}
    >
      <strong style={{ display: "block", marginBottom: 6, fontSize: 13 }}>Exact rule</strong>
      {rule.description ? (
        <p style={{ margin: "0 0 8px", fontSize: 14 }}>{rule.description}</p>
      ) : null}
      <p style={{ margin: 0, fontSize: 14, color: color.text.secondary }}>
        {directionLabel(rule.direction)}. {scopeLabel(rule.max_scope)}.
      </p>
      {rule.source === "builtin" ? (
        <p style={{ margin: "8px 0 0", fontSize: 14, color: color.text.secondary }}>
          This phrase ships with LEO. You cannot edit it here.
        </p>
      ) : null}
      {canDeactivate ? (
        <fm.button
          type="button"
          onClick={() => onDeactivate(rule)}
          whileTap={tapScale(reducedMotion)}
          transition={springOrInstant(reducedMotion, springs.press)}
          style={{
            marginTop: 10,
            border: "1px solid " + color.status.warning,
            background: "rgba(180, 83, 9, 0.1)",
            color: color.status.warning,
            borderRadius: 8,
            padding: "6px 10px",
            fontWeight: 600,
            cursor: "pointer",
            fontFamily: typography.fontFamily.body,
          }}
        >
          Deactivate
        </fm.button>
      ) : null}
    </div>
  );
}

function CategoryLeftColumn({
  copy,
  rules,
  selectedRule,
  onSelect,
  onDeactivate,
}: {
  copy: CategoryCopy;
  rules: ContextRule[];
  selectedRule: ContextRule | null;
  onSelect: (rule: ContextRule) => void;
  onDeactivate: (rule: ContextRule) => void;
}) {
  return (
    <div
      style={{
        width: "52%",
        overflow: "auto",
        padding: 20,
        borderRight: "1px solid " + color.text.secondary,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <CategoryDocs copy={copy} />
        <div>
          <strong style={{ display: "block", marginBottom: 6, fontSize: 13 }}>
            Trigger phrases
          </strong>
          {rules.map((rule) => (
            <ContextPhraseRow
              key={rule.rule_id ?? rule.literal}
              rule={rule}
              selected={
                selectedRule?.literal === rule.literal
                && selectedRule?.source === rule.source
              }
              onSelect={onSelect}
            />
          ))}
        </div>
        {selectedRule ? (
          <SelectedRuleDetail rule={selectedRule} onDeactivate={onDeactivate} />
        ) : null}
      </div>
    </div>
  );
}

function dialogSlots(frost: ReturnType<typeof frostStyle>) {
  return {
    backdrop: {
      sx: {
        backgroundColor: color.surface.overlay,
        backdropFilter: frost.backdropFilter === "none" ? "none" : "blur(16px)",
      },
    },
    paper: {
      sx: {
        width: "min(96vw, calc(90vh * 16 / 9))",
        height: "min(90vh, calc(96vw * 9 / 16))",
        maxWidth: "none",
        maxHeight: "90vh",
        aspectRatio: "16 / 9",
        borderRadius: "16px",
        overflow: "hidden",
        boxShadow: elevation.modal,
        background: frost.background,
        backdropFilter: frost.backdropFilter,
        WebkitBackdropFilter: frost.WebkitBackdropFilter,
        border: "1px solid rgba(255, 255, 255, 0.7)",
      },
    },
  };
}

export default function ContextCategoryDialog({
  copy,
  rules,
  selectedRule,
  onSelect,
  onClose,
  onDeactivate,
}: ContextCategoryDialogProps) {
  const titleId = useId();
  const frost = frostStyle(useReducedTransparency(), "pane");
  const example = resolveContextExample(copy, selectedRule);

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth={false}
      aria-labelledby={titleId}
      slotProps={dialogSlots(frost)}
    >
      <ContextDialogTitleBar titleId={titleId} title={copy.title} onClose={onClose} />
      <DialogContent sx={{ display: "flex", p: 0, overflow: "hidden", height: "100%" }}>
        <CategoryLeftColumn
          copy={copy}
          rules={rules}
          selectedRule={selectedRule}
          onSelect={onSelect}
          onDeactivate={onDeactivate}
        />
        <div
          style={{
            width: "48%",
            overflow: "auto",
            padding: 20,
            background: color.surface.alt,
          }}
        >
          <SpringSwap swapKey={selectedRule?.literal || copy.key}>
            <ContextExamplePanel example={example} />
          </SpringSwap>
        </div>
      </DialogContent>
    </Dialog>
  );
}
