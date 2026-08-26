/**
 * One editable section in Teach this form.
 *
 * Atlas trace: DI-5C9CA57B
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import {
  type FormSchemaItem,
  type FormSchemaSection,
  type SectionType,
} from "./formSchemaDetector";

export const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  checkbox_single: "Single-choice checkboxes",
  checkbox_yesno: "Yes / No pairs",
  checkbox_multi: "Multiple-choice checkboxes",
  free_text: "Free-text narrative (extract as-is)",
  scale: "Ordinal scale",
  ordered_tests: "Tests ordered (no results yet)",
  observable: "Measured value (BMI, BP, HR)",
  admin: "Admin / demographics (skip)",
  template_noise: "Template guidance text (skip)",
};

const ITEM_SECTION_TYPES: SectionType[] = [
  "checkbox_single",
  "checkbox_yesno",
  "checkbox_multi",
  "scale",
  "observable",
];

export function FormSchemaSectionEditor({
  section,
  onPatch,
  onPatchItem,
  onAddItem,
  onRemoveItem,
  focused = false,
  onSelect,
}: {
  section: FormSchemaSection;
  onPatch: (patch: Partial<FormSchemaSection>) => void;
  onPatchItem: (iIdx: number, patch: Partial<FormSchemaItem>) => void;
  onAddItem: () => void;
  onRemoveItem: (iIdx: number) => void;
  focused?: boolean;
  onSelect?: () => void;
}) {
  const [expanded, setExpanded] = useState(
    ITEM_SECTION_TYPES.includes(section.section_type),
  );
  const showItems = ITEM_SECTION_TYPES.includes(section.section_type);

  return (
    <SectionCardFrame
      section={section}
      focused={focused}
      onSelect={onSelect}
      onExpand={() => setExpanded(true)}
      onToggleExpand={() => setExpanded((open) => !open)}
    >
      <Stack
        direction="row"
        alignItems="center"
        sx={{ px: 1.5, py: 1, bgcolor: "action.hover", gap: 1 }}
      >
        <IconButton
          size="small"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? "Collapse section" : "Expand section"}
        >
          <ExpandMoreIcon
            fontSize="small"
            sx={{
              transform: expanded ? "rotate(180deg)" : "none",
              transition: "transform 0.2s",
            }}
          />
        </IconButton>
        <TextField
          label="Section name"
          value={section.label}
          onChange={(e) => onPatch({ label: e.target.value })}
          size="small"
          sx={{ flex: 1, minWidth: 0 }}
        />
        <Select
          value={section.section_type}
          onChange={(e) =>
            onPatch({ section_type: e.target.value as SectionType, items: [] })
          }
          size="small"
          aria-label="Section type"
          sx={{ minWidth: 220, fontSize: "0.75rem" }}
        >
          {(Object.keys(SECTION_TYPE_LABELS) as SectionType[]).map((t) => (
            <MenuItem key={t} value={t} sx={{ fontSize: "0.75rem" }}>
              {SECTION_TYPE_LABELS[t]}
            </MenuItem>
          ))}
        </Select>
      </Stack>
      {showItems ? (
        <Collapse in={expanded}>
          <Box sx={{ p: 1.5 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mb: 1, display: "block" }}
            >
              For each option: enter the label pattern that appears in the form,
              and the entity text to use when it is checked.
            </Typography>
            {section.items.map((item, iIdx) => (
              <ItemRow
                key={iIdx}
                item={item}
                onPatch={(patch) => onPatchItem(iIdx, patch)}
                onRemove={() => onRemoveItem(iIdx)}
              />
            ))}
            <Button
              size="small"
              startIcon={<AddIcon />}
              onClick={onAddItem}
              sx={{ mt: 0.5 }}
            >
              Add item
            </Button>
          </Box>
        </Collapse>
      ) : (
        <Collapse in={expanded}>
          <Box sx={{ px: 2, py: 1 }}>
            <Chip
              label={SECTION_TYPE_LABELS[section.section_type]}
              size="small"
              variant="outlined"
              color={
                section.section_type === "free_text" ? "primary" : "default"
              }
            />
          </Box>
        </Collapse>
      )}
      <Divider />
    </SectionCardFrame>
  );
}

function SectionCardFrame({
  section,
  focused,
  onSelect,
  onExpand,
  onToggleExpand,
  children,
}: {
  section: FormSchemaSection;
  focused: boolean;
  onSelect?: () => void;
  onExpand: () => void;
  onToggleExpand: () => void;
  children: React.ReactNode;
}) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!focused) return;
    onExpand();
    cardRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
    cardRef.current?.focus();
    // Only react when focus arrives, not when the expand callback identity changes.
  }, [focused]);

  return (
    <Box
      ref={cardRef}
      component="article"
      tabIndex={0}
      data-testid="form-schema-section-card"
      data-section-id={section.section_id}
      aria-label={`Form section ${section.section_id}: ${section.label}`}
      aria-current={focused ? "true" : undefined}
      onClick={() => onSelect?.()}
      onKeyDown={(event) => {
        if (isTypingTarget(event.target)) return;
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        onToggleExpand();
        onSelect?.();
      }}
      sx={sectionCardSx(focused)}
    >
      {children}
    </Box>
  );
}

function sectionCardSx(focused: boolean) {
  return {
    mb: 1.5,
    border: "2px solid",
    borderColor: focused ? "primary.main" : "divider",
    outline: focused ? "2px solid" : "none",
    outlineColor: focused ? "primary.main" : undefined,
    outlineOffset: focused ? "1px" : undefined,
    borderRadius: "6px",
    overflow: "hidden",
  };
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement ||
    Boolean(target.closest("[role='combobox']"))
  );
}

function ItemRow({
  item,
  onPatch,
  onRemove,
}: {
  item: FormSchemaItem;
  onPatch: (patch: Partial<FormSchemaItem>) => void;
  onRemove: () => void;
}) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
      <TextField
        label="Label pattern"
        value={item.pattern}
        onChange={(e) => onPatch({ pattern: e.target.value })}
        size="small"
        sx={{ flex: 1 }}
        placeholder="e.g. Cervix"
      />
      <TextField
        label="Entity text when checked"
        value={item.entity_text}
        onChange={(e) => onPatch({ entity_text: e.target.value })}
        size="small"
        sx={{ flex: 2 }}
        placeholder="e.g. Cervical cancer suspected"
      />
      <IconButton size="small" onClick={onRemove} aria-label="Remove item">
        <DeleteIcon fontSize="small" />
      </IconButton>
    </Stack>
  );
}
