/**
 * FormSchemaAnnotator - Teach the pipeline how to process a structured form.
 *
 * Persists the result as a :FormSchema node via PUT /api/form-schemas/{fingerprint}.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721, DO-D0C19842, DO-020C7B5C
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import SchoolIcon from "@mui/icons-material/School";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";

import { useEffect, useState } from "react";
import { FormSchemaCompletenessEditor } from "./FormSchemaCompletenessEditor";
import { FormSchemaScopeFields } from "./FormSchemaScopeFields";
import { FormSchemaSectionEditor } from "./FormSchemaSectionEditor";
import type { FormSchemaSection } from "./formSchemaDetector";
import { seedCompletenessGroups } from "./formSchemaCompletenessSeed";
import { saveTaughtForm, type CompletenessLogicGroup } from "./formSchemaTeach";
import { useFormSchemaTeach } from "./useFormSchemaTeach";
import { FormSchemaDetectionNotice } from "./FormSchemaDetectionNotice";

interface Props {
  fingerprint: string;
  sourceText: string;
  formName?: string;
  onSaved?: () => void;
  focusedSectionId?: string | null;
  onSelectSection?: (section: FormSchemaSection) => void;
  onSectionsChange?: (sections: FormSchemaSection[]) => void;
  pendingSelection?: { pattern: string; entity_text: string; sectionId: string } | null;
  onPendingConsumed?: () => void;
  initialOrganizationId?: string;
  initialServiceId?: string;
  initialOrganizationName?: string;
  initialServiceName?: string;
}

export default function FormSchemaAnnotator({
  fingerprint,
  sourceText,
  formName = "Referral form",
  onSaved,
  focusedSectionId = null,
  onSelectSection,
  onSectionsChange,
  pendingSelection = null,
  onPendingConsumed,
  initialOrganizationId = "",
  initialServiceId = "",
  initialOrganizationName = "",
  initialServiceName = "",
}: Props) {
  const teach = useFormSchemaTeach(fingerprint, sourceText, formName, onSaved, {
    organizationId: initialOrganizationId,
    serviceId: initialServiceId,
  });
  const [organizationId, setOrganizationId] = useState(initialOrganizationId);
  const [serviceId, setServiceId] = useState(initialServiceId);
  const scopeLocked = Boolean(initialOrganizationId || initialServiceId);
  const [groups, setGroups] = useState<CompletenessLogicGroup[]>([]);
  const [scopeSaving, setScopeSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [template, setTemplate] = useState<string | null>(null);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateError, setTemplateError] = useState("");
  const [copied, setCopied] = useState(false);

  const handleGenerateTemplate = async () => {
    setTemplateLoading(true);
    setTemplateError("");
    try {
      const res = await fetch(`/api/form-schemas/${fingerprint}/template`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ text: sourceText }),
      });
      if (!res.ok) throw new Error("generate");
      const data = (await res.json()) as { normalised_template: string };
      setTemplate(data.normalised_template);
    } catch {
      setTemplateError("Could not generate the template. Try again.");
    } finally {
      setTemplateLoading(false);
    }
  };

  const handleCopy = () => {
    if (!template) return;
    void navigator.clipboard.writeText(template).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  useEffect(() => {
    if (!pendingSelection) return;
    const sIdx = teach.sections.findIndex(
      (s) => s.section_id === pendingSelection.sectionId,
    );
    if (sIdx < 0) return;
    teach.addItemWithContent(sIdx, {
      pattern: pendingSelection.pattern,
      entity_text: pendingSelection.entity_text,
      semantic_tag: "finding",
      assertion: "present",
    });
    onPendingConsumed?.();
  }, [pendingSelection]);

  const handleSave = async () => {
    setScopeSaving(true);
    setSaveError("");
    teach.setSaved(false);
    try {
      await saveTaughtForm({
        fingerprint,
        name: teach.name,
        sections: teach.sections,
        organizationId,
        serviceId,
        organizationName: initialOrganizationName,
        serviceName: initialServiceName,
        completenessGroups: groups,
        sourceText,
      });
      teach.setSaved(true);
      onSaved?.();
    } catch (err) {
      const msg =
        err instanceof Error && err.message.trim()
          ? err.message
          : "Could not save the form schema. Try again.";
      setSaveError(msg);
      teach.setSaved(false);
    } finally {
      setScopeSaving(false);
    }
  };

  useEffect(() => {
    onSectionsChange?.(teach.sections);
  }, [teach.sections, onSectionsChange]);

  useEffect(() => {
    if (!teach.sections.length || groups.length) return;
    setGroups(seedCompletenessGroups(sourceText, teach.sections));
  }, [teach.sections, sourceText, groups.length]);

  if (teach.loading) {
    return (
      <Box
        sx={{ display: "flex", alignItems: "center", gap: 1.5, p: 3, color: "text.secondary" }}
      >
        <CircularProgress size={18} />
        <Typography variant="body2">LEO is reading the form structure...</Typography>
      </Box>
    );
  }

  const canSave =
    !teach.saving &&
    !scopeSaving &&
    teach.sections.length > 0 &&
    Boolean(teach.name.trim());

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <TeachHeader
        name={teach.name}
        organizationId={organizationId}
        serviceId={serviceId}
        organizationName={initialOrganizationName}
        serviceName={initialServiceName}
        libraryFingerprint={teach.libraryFingerprint}
        locked={scopeLocked}
        onName={(value) => {
          teach.setName(value);
          teach.setSaved(false);
        }}
        onOrganization={(id) => {
          setOrganizationId(id);
          teach.setSaved(false);
        }}
        onService={(id) => {
          setServiceId(id);
          teach.setSaved(false);
        }}
      />
      <Box sx={{ flex: 1, overflow: "auto", px: 2, py: 1 }}>
        <FormSchemaDetectionNotice message={teach.notice} />
        {teach.sections.length === 0 ? (
          <EmptyTeachState onAdd={teach.addSection} />
        ) : (
          teach.sections.map((section, sIdx) => (
            <FormSchemaSectionEditor
              key={`${section.section_id}-${sIdx}`}
              section={section}
              focused={focusedSectionId === section.section_id}
              onSelect={() => onSelectSection?.(section)}
              onPatch={(patch) => teach.patchSection(sIdx, patch)}
              onPatchItem={(iIdx, patch) => teach.patchItem(sIdx, iIdx, patch)}
              onAddItem={() => teach.addItem(sIdx)}
              onRemoveItem={(iIdx) => teach.removeItem(sIdx, iIdx)}
              onRemoveSection={() => teach.removeSection(sIdx)}
            />
          ))
        )}
        <FormSchemaCompletenessEditor
          groups={groups}
          onChange={(next) => {
            setGroups(next);
            teach.setSaved(false);
          }}
        />
        {template ? (
          <Box sx={{ mt: 2, mb: 1 }}>
            <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 0.5 }}>
              <Typography variant="caption" fontWeight={600} color="text.secondary">
                De-identified form template
              </Typography>
              <Tooltip title={copied ? "Copied!" : "Copy to clipboard"}>
                <IconButton size="small" onClick={handleCopy} aria-label="Copy template">
                  <ContentCopyIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
            <Box
              component="pre"
              sx={{
                fontFamily: "monospace",
                fontSize: "0.7rem",
                bgcolor: "grey.100",
                border: "1px solid",
                borderColor: "divider",
                borderRadius: "4px",
                p: 1.5,
                maxHeight: 240,
                overflow: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {template}
            </Box>
          </Box>
        ) : null}
        {templateError ? (
          <Typography variant="caption" color="error" sx={{ display: "block", mt: 1 }}>
            {templateError}
          </Typography>
        ) : null}
      </Box>
      <TeachFooter
        error={teach.error || saveError}
        saved={teach.saved}
        saving={teach.saving || scopeSaving}
        canSave={canSave}
        showAddMore={teach.sections.length > 0}
        showGenerateTemplate={teach.saved}
        templateLoading={templateLoading}
        onAdd={teach.addSection}
        onSave={() => void handleSave()}
        onRetry={() => void teach.retryDetect()}
        onGenerateTemplate={() => void handleGenerateTemplate()}
      />
    </Box>
  );
}

function TeachHeader({
  name,
  organizationId,
  serviceId,
  organizationName,
  serviceName,
  libraryFingerprint,
  locked,
  onName,
  onOrganization,
  onService,
}: {
  name: string;
  organizationId: string;
  serviceId: string;
  organizationName?: string;
  serviceName?: string;
  libraryFingerprint?: string;
  locked?: boolean;
  onName: (value: string) => void;
  onOrganization: (id: string) => void;
  onService: (id: string) => void;
}) {
  return (
    <Box sx={{ px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}>
      <Stack direction="row" alignItems="center" gap={1}>
        <SchoolIcon sx={{ color: "primary.main", fontSize: 20 }} />
        <Typography variant="subtitle2" fontWeight={700}>
          Teach this form
        </Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Check the sections below. When you save, we check this form against the letter. Next time, we know the form by its headings.
      </Typography>
      {libraryFingerprint ? (
        <Typography variant="caption" color="primary.main" sx={{ display: "block", mt: 0.5 }}>
          From library: {libraryFingerprint}
        </Typography>
      ) : null}
      <TextField
        label="Form name"
        value={name}
        onChange={(e) => onName(e.target.value)}
        size="small"
        fullWidth
        sx={{ mt: 1 }}
      />
      <FormSchemaScopeFields
        organizationId={organizationId}
        serviceId={serviceId}
        organizationName={organizationName}
        serviceName={serviceName}
        locked={locked}
        onOrganization={onOrganization}
        onService={onService}
      />
    </Box>
  );
}

function EmptyTeachState({ onAdd }: { onAdd: () => void }) {
  return (
    <Stack spacing={1.5} sx={{ mt: 2 }}>
      <Typography variant="body2" color="text.secondary">
        LEO did not find sections automatically. Add a section to teach this form.
      </Typography>
      <Button
        variant="contained"
        onClick={onAdd}
        size="small"
        startIcon={<AddIcon />}
        sx={{ alignSelf: "flex-start" }}
      >
        Add section
      </Button>
    </Stack>
  );
}

function TeachFooter({
  error,
  saved,
  saving,
  canSave,
  showAddMore,
  showGenerateTemplate,
  templateLoading,
  onAdd,
  onSave,
  onRetry,
  onGenerateTemplate,
}: {
  error: string;
  saved: boolean;
  saving: boolean;
  canSave: boolean;
  showAddMore: boolean;
  showGenerateTemplate: boolean;
  templateLoading: boolean;
  onAdd: () => void;
  onSave: () => void;
  onRetry: () => void;
  onGenerateTemplate: () => void;
}) {
  return (
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
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Button variant="outlined" onClick={onRetry} size="small">
          Ask LEO again
        </Button>
        {showAddMore ? (
          <Button
            variant="outlined"
            onClick={onAdd}
            size="small"
            startIcon={<AddIcon />}
          >
            Add section
          </Button>
        ) : null}
        <Button
          variant="contained"
          onClick={onSave}
          disabled={!canSave}
          size="small"
          startIcon={saving ? <CircularProgress size={14} color="inherit" /> : undefined}
        >
          {saving ? "Saving schema..." : "Save schema"}
        </Button>
        {showGenerateTemplate ? (
          <Button
            variant="outlined"
            onClick={onGenerateTemplate}
            disabled={templateLoading}
            size="small"
            startIcon={
              templateLoading ? (
                <CircularProgress size={14} color="inherit" />
              ) : undefined
            }
          >
            {templateLoading ? "Generating..." : "Generate template"}
          </Button>
        ) : null}
      </Stack>
    </Box>
  );
}
