/**
 * Context-then-kind tree of extracted facts.
 *
 * Atlas: DI-49BA8E04 / DI-42EB69CA / DO-DD92B11E / VT-592D30E9 / VT-E8A064C9
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { FactLeaf, FactTagGroup, FactTreeGroup } from "./factTree";

interface Props {
  groups: FactTreeGroup[];
  openAssertion: string | null;
  openTag: string | null;
  selectedText: string;
  onToggleAssertion: (key: string) => void;
  onToggleTag: (assertion: string, tag: string) => void;
  onSelectLeaf: (leaf: FactLeaf, assertion: string, tag: string) => void;
  onMarkWrong?: (text: string) => void;
}

export function FactTree({
  groups,
  openAssertion,
  openTag,
  selectedText,
  onToggleAssertion,
  onToggleTag,
  onSelectLeaf,
  onMarkWrong,
}: Props) {
  return (
    <Box
      sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 1.5 }}
      data-testid="validation-lab-fact-tree"
    >
      <Stack spacing={0.5}>
        {groups.map((group) => (
          <AssertionNode
            key={group.key}
            group={group}
            open={openAssertion === group.key}
            openTag={openAssertion === group.key ? openTag : null}
            selectedText={selectedText}
            onToggle={() => onToggleAssertion(group.key)}
            onToggleTag={(tag) => onToggleTag(group.key, tag)}
            onSelectLeaf={(leaf, tag) => onSelectLeaf(leaf, group.key, tag)}
            onMarkWrong={onMarkWrong}
          />
        ))}
      </Stack>
    </Box>
  );
}

function AssertionNode({
  group,
  open,
  openTag,
  selectedText,
  onToggle,
  onToggleTag,
  onSelectLeaf,
  onMarkWrong,
}: {
  group: FactTreeGroup;
  open: boolean;
  openTag: string | null;
  selectedText: string;
  onToggle: () => void;
  onToggleTag: (tag: string) => void;
  onSelectLeaf: (leaf: FactLeaf, tag: string) => void;
  onMarkWrong?: (text: string) => void;
}) {
  return (
    <Box>
      <TreeButton
        label={`${group.label} (${group.count})`}
        open={open}
        disabled={group.count === 0}
        onClick={onToggle}
      />
      {open
        ? group.tags.map((tag) => (
            <TagNode
              key={tag.key}
              tag={tag}
              open={openTag === tag.key}
              selectedText={selectedText}
              onToggle={() => onToggleTag(tag.key)}
              onSelectLeaf={(leaf) => onSelectLeaf(leaf, tag.key)}
              onMarkWrong={onMarkWrong}
            />
          ))
        : null}
    </Box>
  );
}

function TagNode({
  tag,
  open,
  selectedText,
  onToggle,
  onSelectLeaf,
  onMarkWrong,
}: {
  tag: FactTagGroup;
  open: boolean;
  selectedText: string;
  onToggle: () => void;
  onSelectLeaf: (leaf: FactLeaf) => void;
  onMarkWrong?: (text: string) => void;
}) {
  return (
    <Box sx={{ pl: 1.5 }}>
      <TreeButton
        label={`${tag.label} (${tag.count})`}
        open={open}
        onClick={onToggle}
      />
      {open
        ? tag.leaves.map((leaf) => (
            <LeafNode
              key={`${leaf.text}-${leaf.code || ""}`}
              leaf={leaf}
              selected={selectedText.toLowerCase() === leaf.text.toLowerCase()}
              onSelect={() => onSelectLeaf(leaf)}
              onMarkWrong={onMarkWrong}
            />
          ))
        : null}
    </Box>
  );
}

function LeafNode({
  leaf,
  selected,
  onSelect,
  onMarkWrong,
}: {
  leaf: FactLeaf;
  selected: boolean;
  onSelect: () => void;
  onMarkWrong?: (text: string) => void;
}) {
  return (
    <Box sx={{ pl: 3, py: 0.5 }}>
      <ButtonBase
        onClick={onSelect}
        sx={{
          display: "block",
          width: "100%",
          textAlign: "left",
          py: 0.5,
          borderRadius: "6px",
          bgcolor: selected ? "#EEF2FF" : "transparent",
        }}
        data-testid="validation-lab-fact-leaf"
      >
        <Typography variant="body2">{leaf.text}</Typography>
        {leaf.code ? (
          <Typography variant="caption" color="text.secondary" display="block">
            {leaf.code}
          </Typography>
        ) : null}
        {leaf.value ? (
          <Typography variant="caption" color="text.secondary" display="block">
            {[leaf.value, leaf.unit].filter(Boolean).join(" ")}
          </Typography>
        ) : null}
        {leaf.relation ? (
          <Typography variant="caption" color="text.secondary" display="block">
            {leaf.relation}
          </Typography>
        ) : null}
      </ButtonBase>
      {selected && onMarkWrong ? (
        <Button
          size="small"
          onClick={() => onMarkWrong(leaf.text)}
          data-testid="validation-lab-mark-wrong-leaf"
        >
          This is wrong
        </Button>
      ) : null}
    </Box>
  );
}

function TreeButton({
  label,
  open,
  disabled,
  onClick,
}: {
  label: string;
  open: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <ButtonBase
      onClick={onClick}
      disabled={disabled}
      aria-expanded={open}
      sx={{
        display: "block",
        width: "100%",
        textAlign: "left",
        px: 1,
        py: 0.75,
        borderRadius: "6px",
        fontWeight: 600,
      }}
    >
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        {open ? "v " : "> "}
        {label}
      </Typography>
    </ButtonBase>
  );
}
