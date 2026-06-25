/**
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-64CA7740
 */
"use client";

import { use, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Skeleton from "@mui/material/Skeleton";
import Alert from "@mui/material/Alert";
import TemplateEditor from "@/components/audit-template-builder/TemplateEditor";
import { fetchTemplate, type AuditTemplate } from "@/lib/auditTemplateApi";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function EditTemplatePage({ params }: PageProps) {
  const { id } = use(params);
  const [template, setTemplate] = useState<AuditTemplate | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchTemplate(id)
      .then((t) => {
        setTemplate(t);
        if (!t) setError("Template not found");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Skeleton variant="rounded" height={48} width={340} />
        <Skeleton variant="rounded" height={500} />
      </Box>
    );
  }

  if (error || !template) {
    return <Alert severity="error" sx={{ m: 3 }}>{error ?? "Template not found"}</Alert>;
  }

  return <TemplateEditor initial={template} />;
}
