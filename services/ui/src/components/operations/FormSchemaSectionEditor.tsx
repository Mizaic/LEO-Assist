/**
 * One editable section in Teach this form.
 *
 * Atlas trace: DI-5C9CA57B
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
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
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

import { SnomedLookupField } from "@/components/SnomedLookupField";

import { BloodPanelPresetButton } from "./BloodPanelPresetButton";
import { mergePresetBatteries } from "./bloodPanelPresets";
import {
  type AnalyteEntry,
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

// Default SNOMED semantic tags inferred from section type.
// The user can add or remove tags for a section.
export const SECTION_TYPE_SNOMED_TAG: Record<SectionType, string[]> = {
  checkbox_single: ["situation"],
  checkbox_yesno: ["finding"],
  checkbox_multi: ["finding"],
  free_text: ["finding"],
  scale: ["observable"],
  ordered_tests: ["procedure"],
  observable: ["observable"],
  admin: ["none"],
  template_noise: ["none"],
};

const SNOMED_TAG_OPTIONS = [
  "finding",
  "observable",
  "procedure",
  "situation",
  "substance",
  "disorder",
  "none",
];

const ITEM_SECTION_TYPES: SectionType[] = [
  "checkbox_single",
  "checkbox_yesno",
  "checkbox_multi",
  "scale",
  "observable",
  "ordered_tests",
];

export function FormSchemaSectionEditor({
  section,
  onPatch,
  onPatchItem,
  onAddItem,
  onRemoveItem,
  onRemoveSection,
  focused = false,
  onSelect,
}: {
  section: FormSchemaSection;
  onPatch: (patch: Partial<FormSchemaSection>) => void;
  onPatchItem: (iIdx: number, patch: Partial<FormSchemaItem>) => void;
  onAddItem: () => void;
  onRemoveItem: (iIdx: number) => void;
  onRemoveSection?: () => void;
  focused?: boolean;
  onSelect?: () => void;
}) {
  const [expanded, setExpanded] = useState(
    ITEM_SECTION_TYPES.includes(section.section_type),
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
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
          onChange={(e) => {
            const newType = e.target.value as SectionType;
            onPatch({
              section_type: newType,
              items: [],
              semantic_tags: SECTION_TYPE_SNOMED_TAG[newType],
            });
          }}
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
        <SnomedTagSelect
          value={
            section.semantic_tags ??
            SECTION_TYPE_SNOMED_TAG[section.section_type]
          }
          onChange={(tags) => onPatch({ semantic_tags: tags })}
        />
        {onRemoveSection ? (
          confirmDelete ? (
            <Stack direction="row" alignItems="center" gap={0.5} sx={{ flexShrink: 0 }}>
              <Typography variant="caption" color="error" sx={{ whiteSpace: "nowrap" }}>
                Remove section?
              </Typography>
              <Button
                size="small"
                color="error"
                variant="contained"
                sx={{ minWidth: 0, px: 1, py: 0.25, fontSize: "0.7rem" }}
                onClick={() => { setConfirmDelete(false); onRemoveSection(); }}
              >
                Yes
              </Button>
              <Button
                size="small"
                sx={{ minWidth: 0, px: 1, py: 0.25, fontSize: "0.7rem" }}
                onClick={() => setConfirmDelete(false)}
              >
                No
              </Button>
            </Stack>
          ) : (
            <Tooltip title="Remove section">
              <IconButton
                size="small"
                aria-label="Remove section"
                onClick={() => setConfirmDelete(true)}
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          )
        ) : null}
      </Stack>
      {showItems ? (
        <Collapse in={expanded}>
          <Box sx={{ p: 1.5 }}>
            {section.section_type === "ordered_tests" ? (
              <>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mb: 1, display: "block" }}
                >
                  For each blood test battery: enter the label, procedure
                  SNOMED code, and the individual analytes (test result rows).
                </Typography>
                <BloodPanelPresetButton
                  onAdd={(items) =>
                    onPatch({
                      items: mergePresetBatteries(section.items, items),
                    })
                  }
                />
                {section.items.map((item, iIdx) => (
                  <OrderedTestsItemEditor
                    key={iIdx}
                    item={item}
                    onPatch={(patch) => onPatchItem(iIdx, patch)}
                    onRemove={() => onRemoveItem(iIdx)}
                  />
                ))}
              </>
            ) : (
              <>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mb: 1, display: "block" }}
                >
                  For each option: enter the label pattern that appears in the
                  form, and the entity text to use when it is checked.
                </Typography>
                {section.items.map((item, iIdx) => (
                  <ItemRow
                    key={iIdx}
                    item={item}
                    onPatch={(patch) => onPatchItem(iIdx, patch)}
                    onRemove={() => onRemoveItem(iIdx)}
                  />
                ))}
              </>
            )}
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
            {section.section_type === "free_text" ? (
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                The heading is often on one line and the clinical text sits in a
                box on the lines below. All lines after the heading until the
                next section are kept for extraction.
              </Typography>
            ) : null}
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

function SnomedTagSelect({
  value,
  onChange,
}: {
  value: string[];
  onChange: (tags: string[]) => void;
}) {
  return (
    <Autocomplete
      multiple
      size="small"
      options={SNOMED_TAG_OPTIONS}
      value={value}
      onChange={(_e, newValue) => onChange(newValue)}
      disableClearable={false}
      sx={{ minWidth: 220, flexShrink: 0 }}
      renderTags={(selected, getTagProps) =>
        selected.map((tag, index) => (
          <Chip
            {...getTagProps({ index })}
            key={tag}
            label={tag}
            size="small"
            variant="outlined"
            color="secondary"
            sx={{ fontSize: "0.7rem" }}
            data-testid="snomed-tag-chip"
          />
        ))
      }
      renderInput={(params) => (
        <TextField
          {...params}
          label="SNOMED tags"
          size="small"
          sx={{ fontSize: "0.75rem" }}
          inputProps={{
            ...params.inputProps,
            "aria-label": "SNOMED tags",
          }}
        />
      )}
    />
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

function OrderedTestsItemEditor({
  item,
  onPatch,
  onRemove,
}: {
  item: FormSchemaItem;
  onPatch: (patch: Partial<FormSchemaItem>) => void;
  onRemove: () => void;
}) {
  const analytes: AnalyteEntry[] = item.analytes ?? [];

  function patchAnalyte(idx: number, patch: Partial<AnalyteEntry>) {
    const updated = analytes.map((a, i) => (i === idx ? { ...a, ...patch } : a));
    onPatch({ analytes: updated });
  }

  function addAnalyte() {
    onPatch({ analytes: [...analytes, { label: "", snomed_code: "", display: "" }] });
  }

  function removeAnalyte(idx: number) {
    onPatch({ analytes: analytes.filter((_, i) => i !== idx) });
  }

  return (
    <Box
      sx={{ mb: 1.5, p: 1, border: "1px solid", borderColor: "divider", borderRadius: 1 }}
      data-testid="ordered-tests-item-editor"
    >
      <Stack direction="row" spacing={1} alignItems="flex-start" sx={{ mb: 1 }}>
        <TextField
          label="Battery label pattern"
          value={item.pattern}
          onChange={(e) => onPatch({ pattern: e.target.value })}
          size="small"
          sx={{ flex: 1 }}
          placeholder="e.g. FBC"
        />
        <SnomedLookupField
          label="Procedure SNOMED"
          ariaLabel="Procedure SNOMED code"
          semanticTags={["procedure"]}
          testId="procedure-snomed-lookup"
          placeholder="e.g. full blood count"
          value={{
            conceptId: item.procedure_snomed ?? "",
            display: item.procedure_display ?? "",
          }}
          onChange={(next) =>
            onPatch({
              procedure_snomed: next.conceptId,
              procedure_display: next.display,
            })
          }
        />
        <TextField
          label="Procedure display name"
          value={item.procedure_display ?? ""}
          onChange={(e) => onPatch({ procedure_display: e.target.value })}
          size="small"
          sx={{ flex: 2 }}
          placeholder="e.g. Full blood count"
        />
        <IconButton size="small" onClick={onRemove} aria-label="Remove test battery">
          <DeleteIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
        Analytes (individual result rows in this battery)
      </Typography>
      {analytes.map((analyte, aIdx) => (
        <Stack
          key={aIdx}
          direction="row"
          spacing={1}
          alignItems="center"
          sx={{ mb: 0.5 }}
          data-testid="analyte-row"
        >
          <TextField
            label="Short label"
            value={analyte.label}
            onChange={(e) => patchAnalyte(aIdx, { label: e.target.value })}
            size="small"
            sx={{ flex: 1 }}
            placeholder="e.g. Hb"
            inputProps={{ "aria-label": "Analyte short label" }}
          />
          <SnomedLookupField
            label="Analyte SNOMED"
            ariaLabel="Analyte SNOMED code"
            semanticTags={["observable_entity"]}
            testId="analyte-snomed-lookup"
            placeholder="e.g. haemoglobin"
            value={{
              conceptId: analyte.snomed_code,
              display: analyte.display,
            }}
            onChange={(next) =>
              patchAnalyte(aIdx, {
                snomed_code: next.conceptId,
                display: next.display,
              })
            }
          />
          <TextField
            label="Display name"
            value={analyte.display}
            onChange={(e) => patchAnalyte(aIdx, { display: e.target.value })}
            size="small"
            sx={{ flex: 2 }}
            placeholder="e.g. Haemoglobin"
            inputProps={{ "aria-label": "Analyte display name" }}
          />
          <IconButton
            size="small"
            onClick={() => removeAnalyte(aIdx)}
            aria-label="Remove analyte"
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Button size="small" startIcon={<AddIcon />} onClick={addAnalyte} sx={{ mt: 0.25 }}>
        Add analyte
      </Button>
    </Box>
  );
}
