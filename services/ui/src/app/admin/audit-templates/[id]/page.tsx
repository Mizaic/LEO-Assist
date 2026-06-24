/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-64CA7740
 */
"use client";

import { useEffect, useState } from "react";
import { use } from "react";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import TemplateEditor from "@/components/audit-template-builder/TemplateEditor";
import { listTemplates, type AuditTemplate } from "@/lib/auditTemplateApi";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function EditTemplatePage({ params }: PageProps) {
  const { id } = use(params);
  const [template, setTemplate] = useState<AuditTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listTemplates()
      .then((ts) => {
        const found = ts.find((t) => t.template_id === id);
        setTemplate(found ?? null);
        if (!found) setError("Template not found");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", pt: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (error || !template) {
    return <Alert severity="error" sx={{ m: 3 }}>{error ?? "Template not found"}</Alert>;
  }

  return <TemplateEditor initial={template} />;
}
