/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import DOMPurify from "dompurify";
import { fetchDocumentPreview } from "@/lib/patientEprApi";

interface Props {
  patientId: string;
  documentId: string;
}

function sanitizeWordHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["script", "iframe", "object", "embed", "form", "meta", "base"],
  });
}

export function DocumentWordPreviewPane({ patientId, documentId }: Props) {
  const [html, setHtml] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setHtml(null);
    setWarnings([]);
    setError(null);

    void fetchDocumentPreview(patientId, documentId)
      .then((payload) => {
        if (!active) return;
        setHtml(sanitizeWordHtml(payload.html || ""));
        setWarnings(payload.warnings ?? []);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to load Word preview.");
      });

    return () => {
      active = false;
    };
  }, [patientId, documentId]);

  const warningText = useMemo(
    () => warnings.filter(Boolean).slice(0, 3).join(" "),
    [warnings],
  );

  if (error) {
    return (
      <Alert severity="warning" data-testid="document-word-preview-error">
        {error} Use Open in new tab to view the original file.
      </Alert>
    );
  }

  if (!html) {
    return (
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: 320,
          border: "1px solid #E2E8F0",
          borderRadius: "8px",
          bgcolor: "#F8FAFC",
        }}
        data-testid="document-word-preview-loading"
      >
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box data-testid="document-word-preview">
      {warningText && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
          {warnings.some((item) => item.includes("AI-processed text"))
            ? warningText
            : `Some Word formatting may be simplified in preview. ${warningText}`}
        </Typography>
      )}
      <Box
        sx={{
          p: 2,
          border: "1px solid #E2E8F0",
          borderRadius: "8px",
          bgcolor: "#FFFFFF",
          minHeight: 320,
          "& table": { borderCollapse: "collapse", width: "100%", mb: 2 },
          "& td, & th": { border: "1px solid #E2E8F0", p: 1, verticalAlign: "top" },
          "& p": { mb: 1.5 },
          "& ul, & ol": { pl: 3, mb: 1.5 },
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </Box>
  );
}
