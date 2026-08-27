/**
 * Form schemas -- list and edit taught referral forms without a pipeline pause.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import EditIcon from "@mui/icons-material/Edit";
import { StatHero, type StatTile } from "@leo/design-system";

import FormSchemaTeachDialog from "./FormSchemaTeachDialog";

interface SchemaSummary {
  schema_id: string;
  fingerprint: string;
  form_name: string;
  status: string;
  created_at: string;
  organization_id: string;
  service_id: string;
}

async function fetchSchemas(): Promise<SchemaSummary[]> {
  const res = await fetch("/api/form-schemas", {
    credentials: "include",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  });
  if (!res.ok) throw new Error("Could not load form schemas. Please retry.");
  const data = await res.json();
  return data.schemas ?? [];
}

interface SchemaCardProps {
  schema: SchemaSummary;
  onEdit: (schema: SchemaSummary) => void;
  index: number;
}

function SchemaCard({ schema, onEdit, index }: SchemaCardProps) {
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
          {(schema.service_id || schema.organization_id) && (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
              {schema.service_id || schema.organization_id}
            </Typography>
          )}
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexShrink: 0 }}>
          <Chip label={schema.status || "active"} size="small" color="primary" variant="outlined" />
          <Button
            size="small"
            variant="contained"
            startIcon={<EditIcon fontSize="small" />}
            onClick={() => onEdit(schema)}
            aria-label={`Edit schema for ${schema.form_name}`}
          >
            Edit schema
          </Button>
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

  const reload = useCallback(() => {
    setLoading(true);
    setError("");
    fetchSchemas()
      .then(setSchemas)
      .catch((err) => setError(err.message ?? "Could not load form schemas."))
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

  const stats: StatTile[] = useMemo(
    () => [
      {
        id: "schemas",
        label: "Taught forms",
        value: schemas.length,
        hint: "Saved form schemas that skip the quality gate pause",
      },
      {
        id: "active",
        label: "Active",
        value: schemas.filter((s) => (s.status || "active") === "active").length,
        hint: "Schemas currently used at extraction time",
        tone: "positive",
      },
    ],
    [schemas],
  );

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }} data-testid="form-schemas-page">
      <Typography variant="h5" component="h1" sx={{ fontWeight: 700, mb: 0.5 }}>
        Form schemas
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Edit taught referral forms without waiting for a pipeline pause. Paste a
        sample letter, fix sections and blood-test tables, then save.
      </Typography>

      <StatHero stats={stats} />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      <TextField
        size="small"
        placeholder="Search form schemas..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        sx={{ mb: 2, width: 320 }}
        inputProps={{ "aria-label": "Search form schemas" }}
      />

      {loading && (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, color: "text.secondary" }}>
          <CircularProgress size={18} aria-label="Loading" role="status" />
          <Typography variant="body2">Loading form schemas...</Typography>
        </Box>
      )}

      {!loading && !error && schemas.length === 0 && (
        <Alert severity="info">
          No taught form schemas yet. Teach a form from a paused extraction
          review, or save one through the API.
        </Alert>
      )}

      {!loading && !error && schemas.length > 0 && visible.length === 0 && (
        <Alert severity="info">No schemas match this search.</Alert>
      )}

      <Stack spacing={1.5}>
        {visible.map((schema, idx) => (
          <SchemaCard key={schema.schema_id} schema={schema} onEdit={setEditor} index={idx} />
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
    </Box>
  );
}
