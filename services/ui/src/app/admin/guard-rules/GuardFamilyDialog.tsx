/**
 * Family detail dialog -- landscape 16:9.
 * Left: exact rule. Right: with / without example.
 */
"use client";

import { useId, type ReactNode } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import GuardExamplePanel from "./GuardExamplePanel";
import type { GuardFamilyCopy } from "./guardFamilyCopy";
import { familyKind } from "./guardFamilyCopy";
import { resolveWorkedExample } from "./guardWorkedExamples";
import { humanizePattern } from "./humanizePattern";
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

function ruleLabel(rule: NerGuardRule): string {
  return rule.summary || humanizePattern(rule.pattern) || "(no pattern)";
}

function PatternRow({
  rule,
  selected,
  onSelect,
}: {
  rule: NerGuardRule;
  selected: boolean;
  onSelect: (rule: NerGuardRule) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(rule)}
      aria-current={selected ? "true" : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        width: "100%",
        textAlign: "left",
        border: "none",
        borderRadius: 8,
        padding: "8px 10px",
        margin: "2px 0",
        cursor: "pointer",
        background: selected ? "rgba(29,78,216,0.08)" : "transparent",
        font: "inherit",
      }}
    >
      <span
        style={{
          flex: 1,
          fontSize: 13,
          color: "#0F172A",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {ruleLabel(rule)}
      </span>
      <Chip
        size="small"
        label={rule.source === "builtin" ? "Built-in" : "Added"}
        sx={{ height: 18, fontSize: "0.65rem", flexShrink: 0 }}
      />
    </button>
  );
}

function FamilyDocs({ copy }: { copy: GuardFamilyCopy }) {
  return (
    <Stack spacing={0.75}>
      <Typography variant="body2">
        <strong>What it does. </strong>
        {copy.what}
      </Typography>
      <Typography variant="body2">
        <strong>Why it is needed. </strong>
        {copy.why}
      </Typography>
      <Typography variant="body2">
        <strong>If it is wrong. </strong>
        {copy.ifWrong}
      </Typography>
    </Stack>
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
    <Box>
      <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
        {group.label}
      </Typography>
      {group.what && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          {group.what}
        </Typography>
      )}
      {group.rules.map((rule) => (
        <PatternRow
          key={rule.rule_id}
          rule={rule}
          selected={selectedId === rule.rule_id}
          onSelect={onSelect}
        />
      ))}
    </Box>
  );
}

const DIALOG_PAPER_SX = {
  width: "min(96vw, calc(90vh * 16 / 9))",
  height: "min(90vh, calc(96vw * 9 / 16))",
  maxWidth: "none",
  maxHeight: "90vh",
  aspectRatio: "16 / 9",
};

export default function GuardFamilyDialog({
  copy,
  rules,
  selectedRule,
  onSelect,
  onClose,
  editor,
}: GuardFamilyDialogProps) {
  const titleId = useId();
  const example = resolveWorkedExample(
    copy.key,
    selectedRule?.rule_type,
    selectedRule?.pattern,
    selectedRule?.summary,
    selectedRule?.rule_id,
  );

  return (
    <Dialog
      open
      onClose={onClose}
      maxWidth={false}
      aria-labelledby={titleId}
      PaperProps={{ sx: DIALOG_PAPER_SX }}
    >
      <DialogTitle id={titleId} sx={{ pr: 6, py: 1.5 }}>
        {copy.title}
        <Chip size="small" label={familyKind(copy.key)} sx={{ ml: 1, height: 22 }} />
        <IconButton
          aria-label="Close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent
        dividers
        sx={{ display: "flex", p: 0, overflow: "hidden", height: "100%" }}
      >
        <Box
          sx={{
            width: "52%",
            overflow: "auto",
            p: 2.5,
            borderRight: "1px solid #E2E8F0",
          }}
        >
          <Stack spacing={1.5}>
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
          </Stack>
        </Box>
        <Box sx={{ width: "48%", overflow: "auto", p: 2.5, bgcolor: "#F8FAFC" }}>
          <GuardExamplePanel example={example} />
        </Box>
      </DialogContent>
    </Dialog>
  );
}
