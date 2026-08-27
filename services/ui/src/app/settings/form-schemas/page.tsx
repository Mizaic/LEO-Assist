/**
 * Form template library -- list, create, edit, and delete taught referral forms.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditIcon from "@mui/icons-material/Edit";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { StatHero, ToolbarActions, type StatTile, type ToolbarAction } from "@leo/design-system";

import ConfirmDialog from "@/components/ConfirmDialog";
import FormSchemaAddDialog from "./FormSchemaAddDialog";
import FormSchemaTeachDialog from "./FormSchemaTeachDialog";
import {
  deleteFormSchema,
  fetchFormSchemas,
  formatSchemaDate,
  seedFormSchemaDefaults,
  type SchemaSummary,
} from "./formSchemaApi";

interface SchemaCardProps {
  schema: SchemaSummary;
  onEdit: (schema: SchemaSummary) => void;
  onDelete: (schema: SchemaSummary) => void;
  index: number;
}

function SchemaCard({ schema, onEdit, onDelete, index }: SchemaCardProps) {
  return (
    <Box
      sx={{
        position: "relative",
        borderRadius: 12,
        border: "1px solid",
        borderColor: "divider",
        p: "18px",
        minHeight: 80,
        transition: "box-shadow 0.18s ease",
        "&:hover": { boxShadow: "0 2px 12px rgba(0,0,0,0.07)" },
      }}
      style={{ animationDelay: `${Math.min(index, 12) * 40}ms` }}
      data-testid="form-schema-card"
    >
      <span
        aria-hidden="true"
        style={{
          position: "absolute",
          left: 0,
          top: 14,
          bottom: 14,
          width: 3,
          borderRadius: 2,
          background: "#0d46d6",
        }}
      />
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2 }}>
        <Box>
          <Typography variant="subtitle1" fontWeight={700}>
            {schema.form_name}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            {schema.fingerprint}
          </Typography>
          {(schema.organization_id || schema.service_id) && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {[schema.organization_id, schema.service_id].filter(Boolean).join(" / ")}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
            Updated {formatSchemaDate(schema.updated_at || schema.created_at)}
          </Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexShrink: 0 }}>
          <Chip label={schema.status || "active"} size="small" color="primary" variant="outlined" />
          <Button
            size="small"
            variant="contained"
            startIcon={<EditIcon fontSize="small" />}
            onClick={() => onEdit(schema)}
            aria-label={`Edit template for ${schema.form_name}`}
          >
            Edit
          </Button>
          <IconButton
            size="small"
            aria-label={`Delete template for ${schema.form_name}`}
            onClick={() => onDelete(schema)}
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Box>
      </Box>
    </Box>
  );
}

export default function FormSchemasPage() {
  const searchParams = useSearchParams();
  const [schemas, setSchemas] = useState<SchemaSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<SchemaSummary | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SchemaSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [seeding, setSeeding] = useState(false);
  const [seedError, setSeedError] = useState("");
  const [seedNotice, setSeedNotice] = useState("");

  const reload = useCallback(() => {
    setLoading(true);
    setError("");
    fetchFormSchemas()
      .then(setSchemas)
      .catch((err) => setError(err.message ?? "Could not load form templates."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const fp = (searchParams.get("fingerprint") || "").trim();
    if (!fp || loading || schemas.length === 0) return;
    const match = schemas.find((s) => s.fingerprint === fp);
    if (match) setEditor(match);
  }, [searchParams, schemas, loading]);

  const visible = useMemo(() => {
    if (!search.trim()) return schemas;
    const q = search.toLowerCase();
    return schemas.filter(
      (s) =>
        s.form_name.toLowerCase().includes(q) ||
        s.fingerprint.toLowerCase().includes(q) ||
        s.service_id.toLowerCase().includes(q) ||
        s.organization_id.toLowerCase().includes(q),
    );
  }, [schemas, search]);

  const fingerprintSet = useMemo(
    () => new Set(schemas.map((s) => s.fingerprint)),
    [schemas],
  );

  const stats: StatTile[] = useMemo(
    () => [
      {
        id: "schemas",
        label: "Taught forms",
        value: schemas.length,
        hint: "Saved templates that skip the quality gate pause",
      },
      {
        id: "active",
        label: "Active",
        value: schemas.filter((s) => (s.status || "active") === "active").length,
        hint: "Templates currently used at extraction time",
        tone: "positive",
      },
    ],
    [schemas],
  );

  const handleSeedDefaults = useCallback(async () => {
    setSeeding(true);
    setSeedError("");
    setSeedNotice("");
    try {
      const result = await seedFormSchemaDefaults();
      if (result.skipped.length > 0 && result.seeded.length === 0) {
        setSeedNotice("Already present");
      }
      reload();
    } catch (err) {
      setSeedError(
        err instanceof Error ? err.message : "Could not seed the template.",
      );
    } finally {
      setSeeding(false);
    }
  }, [reload]);

  const toolbarActions: ToolbarAction[] = useMemo(
    () => [
      {
        id: "seed-sherwood-gynae-2ww",
        label: "Seed Sherwood Gynae 2WW",
        variant: "secondary",
        disabled: seeding,
        onClick: () => void handleSeedDefaults(),
      },
      {
        id: "add-template",
        label: "Add template",
        icon: <AddIcon fontSize="small" />,
        variant: "primary",
        onClick: () => setAddOpen(true),
      },
    ],
    [handleSeedDefaults, seeding],
  );

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteFormSchema(deleteTarget.fingerprint);
      setDeleteTarget(null);
      reload();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }} data-testid="form-schemas-page">
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Form templates
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Teach referral forms before they pause the pipeline. Add a template,
        fix sections and blood-test tables, then save.
      </Typography>

      <StatHero stats={stats} />

      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 2,
          mb: 2,
        }}
      >
        <TextField
          size="small"
          placeholder="Search form templates..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ width: 320 }}
          inputProps={{ "aria-label": "Search form templates" }}
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {deleteError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {deleteError}
        </Alert>
      )}

      {seedError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {seedError}
        </Alert>
      )}

      {loading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, color: "text.secondary" }}>
          <CircularProgress size={18} aria-label="Loading" role="status" />
          <Typography variant="body2">Loading form templates...</Typography>
        </Box>
      )}

      {!loading && !error && schemas.length === 0 && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            No form templates yet. Add one with a sample letter, or seed the
            Sherwood Gynae 2WW template.
          </Typography>
          <Button
            variant="contained"
            disabled={seeding}
            onClick={() => void handleSeedDefaults()}
          >
            Seed Sherwood Gynae 2WW
          </Button>
        </Alert>
      )}

      {!loading && !error && schemas.length > 0 && visible.length === 0 && (
        <Alert severity="info">No templates match this search.</Alert>
      )}

      <Stack spacing={1.5}>
        {visible.map((schema, idx) => (
          <SchemaCard
            key={schema.schema_id}
            schema={schema}
            onEdit={setEditor}
            onDelete={setDeleteTarget}
            index={idx}
          />
        ))}
      </Stack>

      {editor ? (
        <FormSchemaTeachDialog
          open
          fingerprint={editor.fingerprint}
          formName={editor.form_name}
          organizationId={editor.organization_id}
          serviceId={editor.service_id}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            reload();
          }}
        />
      ) : null}

      {addOpen ? (
        <FormSchemaAddDialog
          open
          existingFingerprints={fingerprintSet}
          onClose={() => setAddOpen(false)}
          onSaved={() => {
            setAddOpen(false);
            reload();
          }}
          onEditExisting={(fingerprint, formName) => {
            setAddOpen(false);
            setEditor({
              schema_id: "",
              fingerprint,
              form_name: formName,
              status: "active",
              created_at: "",
              updated_at: "",
              organization_id: "",
              service_id: "",
            });
          }}
        />
      ) : null}

      {deleteTarget ? (
        <ConfirmDialog
          title="Delete this form template?"
          body={`This removes "${deleteTarget.form_name}" (${deleteTarget.fingerprint}). Live referrals will pause again until you teach the form.`}
          confirmLabel="Delete template"
          variant="danger"
          busy={deleting}
          busyLabel="Deleting..."
          onConfirm={() => void handleDelete()}
          onCancel={() => {
            if (!deleting) setDeleteTarget(null);
          }}
        />
      ) : null}

      <Snackbar
        open={Boolean(seedNotice)}
        autoHideDuration={4000}
        onClose={() => setSeedNotice("")}
        message={seedNotice}
      />
    </Box>
  );
}
