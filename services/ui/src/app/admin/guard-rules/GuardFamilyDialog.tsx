/**
 * Family detail dialog -- landscape 16:9.
 * Left: exact rule. Right: with / without example.
 *
 * Atlas trace:
 *   Implements: DO-6413D5BC
 *   DI: DI-34712A9A, DI-C5A523A7
 */
"use client";

import { useId, type ReactNode } from "react";
import {
  frostStyle,
  SpringSwap,
  useReducedTransparency,
} from "@leo/design-system";
import { color, elevation } from "@leo/design-system/tokens";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";

import { GuardDialogTitleBar } from "./GuardDialogTitleBar";
import GuardExamplePanel from "./GuardExamplePanel";
import { GuardPatternRow } from "./GuardPatternRow";
import type { GuardFamilyCopy } from "./guardFamilyCopy";
import { familyKind } from "./guardFamilyCopy";
import { resolveWorkedExample } from "./guardWorkedExamples";
import type { NerGuardRule } from "./types";

interface GuardFamilyDialogProps {
  copy: GuardFamilyCopy;
  rules: NerGuardRule[];
  selectedRule: NerGuardRule | null;
  onSelect: (rule: NerGuardRule) => void;
  onClose: () => void;
  editor: ReactNode;
}

function typeGroups(rules: NerGuardRule[], copy: GuardFamilyCopy) {
  const groups: Array<{ key: string; label: string; what: string; rules: NerGuardRule[] }> = [];
  const seen = new Set<string>();
  for (const rule of rules) {
    if (seen.has(rule.rule_type)) continue;
    seen.add(rule.rule_type);
    const typeCopy = copy.types[rule.rule_type];
    groups.push({
      key: rule.rule_type,
      label: typeCopy?.label ?? rule.rule_type,
      what: typeCopy?.what ?? "",
      rules: rules.filter((item) => item.rule_type === rule.rule_type),
    });
  }
  return groups;
}

function FamilyDocs({ copy }: { copy: GuardFamilyCopy }) {
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

function PatternGroup({
  group,
  selectedId,
  onSelect,
}: {
  group: { key: string; label: string; what: string; rules: NerGuardRule[] };
  selectedId: string | undefined;
  onSelect: (rule: NerGuardRule) => void;
}) {
  return (
    <div>
      <strong style={{ display: "block", fontSize: 13 }}>{group.label}</strong>
      {group.what ? (
        <p style={{ margin: "4px 0 6px", fontSize: 14, color: color.text.secondary }}>
          {group.what}
        </p>
      ) : null}
      {group.rules.map((rule) => (
        <GuardPatternRow
          key={rule.rule_id}
          rule={rule}
          selected={selectedId === rule.rule_id}
          onSelect={onSelect}
        />
      ))}
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

function FamilyDialogBody({
  copy,
  rules,
  selectedRule,
  onSelect,
  editor,
}: {
  copy: GuardFamilyCopy;
  rules: NerGuardRule[];
  selectedRule: NerGuardRule | null;
  onSelect: (rule: NerGuardRule) => void;
  editor: ReactNode;
}) {
  const example = resolveWorkedExample(
    copy.key,
    selectedRule?.rule_type,
    selectedRule?.pattern,
    selectedRule?.summary,
    selectedRule?.rule_id,
  );
  return (
    <DialogContent sx={{ display: "flex", p: 0, overflow: "hidden", height: "100%" }}>
      <div
        style={{
          width: "52%",
          overflow: "auto",
          padding: 20,
          borderRight: "1px solid " + color.text.secondary,
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <FamilyDocs copy={copy} />
          {typeGroups(rules, copy).map((group) => (
            <PatternGroup
              key={group.key}
              group={group}
              selectedId={selectedRule?.rule_id}
              onSelect={onSelect}
            />
          ))}
          {editor}
        </div>
      </div>
      <div
        style={{
          width: "48%",
          overflow: "auto",
          padding: 20,
          background: color.surface.alt,
        }}
      >
        <SpringSwap swapKey={selectedRule?.rule_id || copy.key}>
          <GuardExamplePanel example={example} />
        </SpringSwap>
      </div>
    </DialogContent>
  );
}

export default function GuardFamilyDialog({
  copy,
  rules,
  selectedRule,
  onSelect,
  onClose,
  editor,
}: GuardFamilyDialogProps) {
  const titleId = useId();
  const frost = frostStyle(useReducedTransparency(), "pane");
  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth={false}
      aria-labelledby={titleId}
      slotProps={dialogSlots(frost)}
    >
      <GuardDialogTitleBar
        titleId={titleId}
        title={copy.title}
        badge={familyKind(copy.key)}
        onClose={onClose}
      />
      <FamilyDialogBody
        copy={copy}
        rules={rules}
        selectedRule={selectedRule}
        onSelect={onSelect}
        editor={editor}
      />
    </Dialog>
  );
}
