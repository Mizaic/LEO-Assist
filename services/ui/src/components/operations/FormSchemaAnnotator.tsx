/**
 * FormSchemaAnnotator - Teach the pipeline how to process a structured form.
 *
 * Persists the result as a :FormSchema node via PUT /api/form-schemas/{fingerprint}.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import SchoolIcon from "@mui/icons-material/School";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";

import { FormSchemaSectionEditor } from "./FormSchemaSectionEditor";
import { useFormSchemaTeach } from "./useFormSchemaTeach";

interface Props {
  fingerprint: string;
  sourceText: string;
  formName?: string;
  onSaved?: () => void;
}

export default function FormSchemaAnnotator({
  fingerprint,
  sourceText,
  formName = "Referral form",
  onSaved,
}: Props) {
  const teach = useFormSchemaTeach(fingerprint, sourceText, formName, onSaved);

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
    !teach.saving && teach.sections.length > 0 && Boolean(teach.name.trim());

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <TeachHeader
        name={teach.name}
        onName={(value) => {
          teach.setName(value);
          teach.setSaved(false);
        }}
      />
      <Box sx={{ flex: 1, overflow: "auto", px: 2, py: 1 }}>
        {teach.sections.length === 0 ? (
          <EmptyTeachState onAdd={teach.addSection} />
        ) : (
          teach.sections.map((section, sIdx) => (
            <FormSchemaSectionEditor
              key={`${section.section_id}-${sIdx}`}
              section={section}
              onPatch={(patch) => teach.patchSection(sIdx, patch)}
              onPatchItem={(iIdx, patch) => teach.patchItem(sIdx, iIdx, patch)}
              onAddItem={() => teach.addItem(sIdx)}
              onRemoveItem={(iIdx) => teach.removeItem(sIdx, iIdx)}
            />
          ))
        )}
      </Box>
      <TeachFooter
        error={teach.error}
        saved={teach.saved}
        saving={teach.saving}
        canSave={canSave}
        showAddMore={teach.sections.length > 0}
        onAdd={teach.addSection}
        onSave={teach.saveSchema}
        onRetry={() => void teach.retryDetect()}
      />
    </Box>
  );
}

function TeachHeader({
  name,
  onName,
}: {
  name: string;
  onName: (value: string) => void;
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
        Confirm the sections below. When you save, this form will never pause again.
      </Typography>
      <TextField
        label="Form name"
        value={name}
        onChange={(e) => onName(e.target.value)}
        size="small"
        fullWidth
        sx={{ mt: 1 }}
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
  onAdd,
  onSave,
  onRetry,
}: {
  error: string;
  saved: boolean;
  saving: boolean;
  canSave: boolean;
  showAddMore: boolean;
  onAdd: () => void;
  onSave: () => void;
  onRetry: () => void;
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
      </Stack>
    </Box>
  );
}
