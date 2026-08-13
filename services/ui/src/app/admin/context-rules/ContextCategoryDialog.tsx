/**
 * Category detail dialog -- landscape 16:9.
 * Left: exact phrases. Right: with / without example.
 */
"use client";

import { useId } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import ContextExamplePanel from "./ContextExamplePanel";
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

function PhraseRow({
  rule,
  selected,
  onSelect,
}: {
  rule: ContextRule;
  selected: boolean;
  onSelect: (rule: ContextRule) => void;
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
          fontFamily: "var(--font-jetbrains-mono), monospace",
        }}
      >
        {rule.literal}
      </span>
      <Chip
        size="small"
        label={rule.source === "builtin" ? "Built-in" : "Added"}
        sx={{ height: 18, fontSize: "0.65rem", flexShrink: 0 }}
      />
    </button>
  );
}

function CategoryDocs({ copy }: { copy: CategoryCopy }) {
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

function SelectedRuleDetail({
  rule,
  onDeactivate,
}: {
  rule: ContextRule;
  onDeactivate: (rule: ContextRule) => void;
}) {
  const canDeactivate = rule.source === "custom" && rule.active && rule.rule_id;
  return (
    <Box sx={{ p: 1.5, border: "1px solid #E2E8F0", borderRadius: "10px" }}>
      <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.75 }}>
        Exact rule
      </Typography>
      {rule.description ? (
        <Typography variant="body2" sx={{ mb: 0.75 }}>
          {rule.description}
        </Typography>
      ) : null}
      <Typography variant="body2" color="text.secondary">
        {directionLabel(rule.direction)}. {scopeLabel(rule.max_scope)}.
      </Typography>
      {rule.source === "builtin" ? (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
          This phrase ships with LEO. You cannot edit it here.
        </Typography>
      ) : null}
      {canDeactivate ? (
        <Button
          size="small"
          color="warning"
          sx={{ mt: 1, textTransform: "none" }}
          onClick={() => onDeactivate(rule)}
        >
          Deactivate
        </Button>
      ) : null}
    </Box>
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
    <Box
      sx={{
        width: "52%",
        overflow: "auto",
        p: 2.5,
        borderRight: "1px solid #E2E8F0",
      }}
    >
      <Stack spacing={1.5}>
        <CategoryDocs copy={copy} />
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
            Trigger phrases
          </Typography>
          {rules.map((rule) => (
            <PhraseRow
              key={rule.rule_id ?? rule.literal}
              rule={rule}
              selected={
                selectedRule?.literal === rule.literal
                && selectedRule?.source === rule.source
              }
              onSelect={onSelect}
            />
          ))}
        </Box>
        {selectedRule ? (
          <SelectedRuleDetail rule={selectedRule} onDeactivate={onDeactivate} />
        ) : null}
      </Stack>
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

export default function ContextCategoryDialog({
  copy,
  rules,
  selectedRule,
  onSelect,
  onClose,
  onDeactivate,
}: ContextCategoryDialogProps) {
  const titleId = useId();
  const example = resolveContextExample(copy, selectedRule);

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
        <Chip size="small" label="Context" sx={{ ml: 1, height: 22 }} />
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
        <CategoryLeftColumn
          copy={copy}
          rules={rules}
          selectedRule={selectedRule}
          onSelect={onSelect}
          onDeactivate={onDeactivate}
        />
        <Box sx={{ width: "48%", overflow: "auto", p: 2.5, bgcolor: "#F8FAFC" }}>
          <ContextExamplePanel example={example} />
        </Box>
      </DialogContent>
    </Dialog>
  );
}
