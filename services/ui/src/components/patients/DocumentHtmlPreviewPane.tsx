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
import DOMPurify from "dompurify";
import { patientDocumentFileUrl } from "@/lib/patientEprApi";
import { looksLikeHtmlBody } from "./documentFormat";
import { wrapClinicalPreviewHtml } from "./clinicalPreviewDocument";

interface Props {
  patientId: string;
  documentId: string;
  inlineHtml?: string;
  title: string;
}

function sanitizeClinicalHtml(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["script", "iframe", "object", "embed", "form", "meta", "base"],
    FORBID_ATTR: ["onerror", "onload", "onclick", "onfocus", "onblur"],
  });
}

function looksLikeHtml(text: string): boolean {
  return looksLikeHtmlBody(text);
}

export function DocumentHtmlPreviewPane({
  patientId,
  documentId,
  inlineHtml,
  title,
}: Props) {
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setHtml(null);
    setError(null);

    if (inlineHtml && looksLikeHtml(inlineHtml)) {
      setHtml(wrapClinicalPreviewHtml(sanitizeClinicalHtml(inlineHtml)));
      return () => {
        active = false;
      };
    }

    const url = patientDocumentFileUrl(patientId, documentId);
    void fetch(url, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          try {
            const body = JSON.parse(text) as { detail?: string };
            if (body.detail) throw new Error(body.detail);
          } catch (parseErr) {
            if (parseErr instanceof Error && parseErr.message !== text) throw parseErr;
          }
          throw new Error(text || `Unable to load HTML (${response.status})`);
        }
        return response.text();
      })
      .then((raw) => {
        if (!active) return;
        setHtml(wrapClinicalPreviewHtml(sanitizeClinicalHtml(raw)));
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to load HTML preview.");
      });

    return () => {
      active = false;
    };
  }, [patientId, documentId, inlineHtml]);

  const safeHtml = useMemo(() => html ?? "", [html]);

  if (error) {
    return (
      <Alert severity="warning" data-testid="document-html-preview-error">
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
        data-testid="document-html-preview-loading"
      >
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box
      sx={{
        minHeight: 480,
        height: "calc(100vh - 320px)",
        border: "1px solid #E2E8F0",
        borderRadius: "8px",
        overflow: "hidden",
        bgcolor: "#FFFFFF",
      }}
      data-testid="document-html-preview"
    >
      <Box
        component="iframe"
        srcDoc={safeHtml}
        sandbox=""
        referrerPolicy="no-referrer"
        title={title}
        sx={{ display: "block", width: "100%", height: "100%", border: "none", bgcolor: "#fff" }}
      />
    </Box>
  );
}
