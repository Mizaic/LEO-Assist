/**
 * FormSchemaAnnotator - Teach the pipeline how to process a structured form.
 *
 * Shows auto-detected sections from the referral text. The clinician can
 * confirm or correct the section type for each section, and for checkbox
 * sections, define what each checked item should produce as a clinical entity.
 *
 * Persists the result as a :FormSchema node in Neo4j via PUT /api/form-schemas/{fingerprint}.
 * Once saved, the pipeline gate is bypassed and extraction is deterministic.
 *
 * Atlas trace: DI-5C9CA57B
 */
"use client";

import { useEffect, useState, useCallback } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
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
import SchoolIcon from "@mui/icons-material/School";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";

import {
  detectSections,
  type FormSchemaSection,
  type FormSchemaItem,
  type SectionType,
} from "./formSchemaDetector";

interface Props {
  fingerprint: string;
  sourceText: string;
  formName?: string;
  onSaved?: () => void;
}

const SECTION_TYPE_LABELS: Record<SectionType, string> = {
  checkbox_single: "Single-choice checkboxes",
  checkbox_yesno: "Yes / No pairs",
  checkbox_multi: "Multiple-choice checkboxes",
  free_text: "Free-text narrative (extract as-is)",
  scale: "Ordinal scale",
  ordered_tests: "Tests ordered (no results yet)",
  admin: "Admin / demographics (skip)",
  template_noise: "Template guidance text (skip)",
};

const ITEM_SECTION_TYPES: SectionType[] = [
  "checkbox_single",
  "checkbox_yesno",
  "checkbox_multi",
  "scale",
];

// ---------------------------------------------------------------------------
// FormSchemaAnnotator
// ---------------------------------------------------------------------------

export default function FormSchemaAnnotator({
  fingerprint,
  sourceText,
  formName = "Referral form",
  onSaved,
}: Props) {
  const [sections, setSections] = useState<FormSchemaSection[]>([]);
  const [name, setName] = useState(formName);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const loadOrDetect = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`/api/form-schemas/${fingerprint}`, {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (res.ok) {
        const payload = await res.json() as { schema: { form_name: string; sections: FormSchemaSection[] } | null };
        if (payload.schema) {
          setName(payload.schema.form_name);
          setSections(payload.schema.sections);
          return;
        }
      }
    } catch {
      // Network error: fall through to auto-detect
    }
    setSections(detectSections(sourceText));
  }, [fingerprint, sourceText]);

  useEffect(() => {
    void loadOrDetect().finally(() => setLoading(false));
  }, [loadOrDetect]);

  async function saveSchema() {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`/api/form-schemas/${fingerprint}`, {
        method: "PUT",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          form_name: name,
          sections,
          saved_by: "validation_lab",
        }),
      });
      if (!res.ok) throw new Error("save");
      setSaved(true);
      onSaved?.();
    } catch {
      setError("Could not save the form schema. Try again.");
    } finally {
      setSaving(false);
    }
  }

  function patchSection(idx: number, patch: Partial<FormSchemaSection>) {
    setSections((prev) =>
      prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)),
    );
    setSaved(false);
  }

  function patchItem(
    sIdx: number,
    iIdx: number,
    patch: Partial<FormSchemaItem>,
  ) {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return {
          ...s,
          items: s.items.map((item, j) =>
            j === iIdx ? { ...item, ...patch } : item,
          ),
        };
      }),
    );
    setSaved(false);
  }

  function addItem(sIdx: number) {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return {
          ...s,
          items: [
            ...s.items,
            {
              pattern: "",
              entity_text: "",
              semantic_tag: "finding",
              assertion: "present",
            },
          ],
        };
      }),
    );
  }

  function removeItem(sIdx: number, iIdx: number) {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return { ...s, items: s.items.filter((_, j) => j !== iIdx) };
      }),
    );
    setSaved(false);
  }

  if (loading) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1.5,
          p: 3,
          color: "text.secondary",
        }}
      >
        <CircularProgress size={18} />
        <Typography variant="body2">Analysing form structure...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      {/* Header */}
      <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}>
        <Stack direction="row" alignItems="center" gap={1}>
          <SchoolIcon sx={{ color: "primary.main", fontSize: 20 }} />
          <Typography variant="subtitle2" fontWeight={700}>
            Teach this form
          </Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Confirm the sections below. When you save, this form will never pause again.
        </Typography>
        <TextField
          label="Form name"
          value={name}
          onChange={(e) => { setName(e.target.value); setSaved(false); }}
          size="small"
          fullWidth
          sx={{ mt: 1 }}
        />
      </Box>

      {/* Section list */}
      <Box sx={{ flex: 1, overflow: "auto", px: 2, py: 1 }}>
        {sections.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            No structured sections detected in this letter.
            The form may be free-text only -- no schema is needed.
          </Typography>
        ) : (
          sections.map((section, sIdx) => (
            <SectionEditor
              key={`${section.section_id}-${sIdx}`}
              section={section}
              onPatch={(patch) => patchSection(sIdx, patch)}
              onPatchItem={(iIdx, patch) => patchItem(sIdx, iIdx, patch)}
              onAddItem={() => addItem(sIdx)}
              onRemoveItem={(iIdx) => removeItem(sIdx, iIdx)}
            />
          ))
        )}
      </Box>

      {/* Footer actions */}
      <Box
        sx={{
          px: 2,
          py: 1.5,
          borderTop: "1px solid",
          borderColor: "divider",
          bgcolor: "#FAFAFA",
          flexShrink: 0,
        }}
      >
        {error ? (
          <Typography variant="caption" color="error" sx={{ display: "block", mb: 1 }}>
            {error}
          </Typography>
        ) : null}
        {saved ? (
          <Stack direction="row" alignItems="center" gap={0.75} sx={{ mb: 1 }}>
            <CheckCircleOutlineIcon sx={{ color: "success.main", fontSize: 18 }} />
            <Typography variant="caption" color="success.main" fontWeight={600}>
              Schema saved. Future runs of this form will not pause.
            </Typography>
          </Stack>
        ) : null}
        <Button
          variant="contained"
          onClick={() => void saveSchema()}
          disabled={saving || sections.length === 0}
          size="small"
          startIcon={saving ? <CircularProgress size={14} color="inherit" /> : undefined}
        >
          {saving ? "Saving schema..." : "Save schema"}
        </Button>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// SectionEditor
// ---------------------------------------------------------------------------

function SectionEditor({
  section,
  onPatch,
  onPatchItem,
  onAddItem,
  onRemoveItem,
}: {
  section: FormSchemaSection;
  onPatch: (patch: Partial<FormSchemaSection>) => void;
  onPatchItem: (iIdx: number, patch: Partial<FormSchemaItem>) => void;
  onAddItem: () => void;
  onRemoveItem: (iIdx: number) => void;
}) {
  const [expanded, setExpanded] = useState(
    ITEM_SECTION_TYPES.includes(section.section_type),
  );
  const showItems = ITEM_SECTION_TYPES.includes(section.section_type);

  return (
    <Box
      sx={{
        mb: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: "6px",
        overflow: "hidden",
      }}
    >
      {/* Section header row */}
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
        <Typography
          variant="caption"
          fontWeight={700}
          sx={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {section.label}
        </Typography>
        <Select
          value={section.section_type}
          onChange={(e) =>
            onPatch({ section_type: e.target.value as SectionType, items: [] })
          }
          size="small"
          sx={{ minWidth: 220, fontSize: "0.75rem" }}
        >
          {(Object.keys(SECTION_TYPE_LABELS) as SectionType[]).map((t) => (
            <MenuItem key={t} value={t} sx={{ fontSize: "0.75rem" }}>
              {SECTION_TYPE_LABELS[t]}
            </MenuItem>
          ))}
        </Select>
      </Stack>

      {/* Items editor */}
      {showItems ? (
        <Collapse in={expanded}>
          <Box sx={{ p: 1.5 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>
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
    </Box>
  );
}

// ---------------------------------------------------------------------------
// ItemRow
// ---------------------------------------------------------------------------

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
