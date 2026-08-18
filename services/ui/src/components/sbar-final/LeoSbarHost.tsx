/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DO: DO-BEE23936
 *   DI: DI-2289D095
 *   DI: DI-B03BD651
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-BEE23936")
 */
"use client";

/**
 * CDN / workspace host for the clinical leo-sbar widget.
 *
 * Atlas: DI-A898556B / DO-158BE606 / DI-B03BD651 / DO-BEE23936
 */

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import PictureAsPdfIcon from "@mui/icons-material/PictureAsPdf";
import { LeoLoader } from "@leo/design-system";

import {
  composeSbarMarkdownFromAssessment,
  exportSbarPdf,
  type SbarAssessmentForPdf,
} from "@/lib/exportSbarPdf";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace React {
    // eslint-disable-next-line @typescript-eslint/no-namespace
    namespace JSX {
      interface IntrinsicElements {
        "leo-sbar": React.DetailedHTMLProps<
          React.HTMLAttributes<HTMLElement>,
          HTMLElement
        > & {
          "assessment-id"?: string;
          "widget-token"?: string;
          "proxy-origin"?: string;
          advisory?: string;
        };
      }
    }
  }
}

export interface LeoSbarHostProps {
  assessmentId: string;
  testId?: string;
}

type ComplianceAlert = {
  alert_type?: string;
  message?: string;
  letter_evidence?: string;
  detector_version?: string;
};

type AssessmentMeta = {
  compliance_alerts?: ComplianceAlert[];
  recall_needs_review?: boolean;
  recall_exhaustion?: {
    missing_flags?: string[];
    needs_review?: boolean;
  };
};

async function fetchAssessmentMeta(
  assessmentId: string,
): Promise<AssessmentMeta> {
  const res = await fetch(
    `/api/sbar/assessments/${encodeURIComponent(assessmentId)}`,
    { credentials: "include", headers: { Accept: "application/json" } },
  );
  if (!res.ok) {
    return {};
  }
  const body = (await res.json().catch(() => ({}))) as AssessmentMeta;
  return body;
}

async function fetchAssessmentForPdf(
  assessmentId: string,
): Promise<SbarAssessmentForPdf> {
  const res = await fetch(
    `/api/sbar/assessments/${encodeURIComponent(assessmentId)}`,
    { credentials: "include", headers: { Accept: "application/json" } },
  );
  const body = (await res.json().catch(() => ({}))) as SbarAssessmentForPdf & {
    detail?: string;
  };
  if (!res.ok) {
    throw new Error(
      body.detail || "Unable to load the SBAR for PDF export. Please retry.",
    );
  }
  return body;
}

export function LeoSbarHost({
  assessmentId,
  testId = "leo-sbar-host",
}: LeoSbarHostProps) {
  const [token, setToken] = useState<string | null>(null);
  const [widgetReady, setWidgetReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [complianceAlerts, setComplianceAlerts] = useState<ComplianceAlert[]>([]);
  const [recallNeedsReview, setRecallNeedsReview] = useState(false);
  const [recallMissingFlags, setRecallMissingFlags] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    void import("@mizaic/leo-widget")
      .then(() => {
        if (!cancelled) setWidgetReady(true);
      })
      .catch(() => {
        if (!cancelled) {
          setError("Unable to load the SBAR viewer. Please retry.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function mint() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch("/api/sdk/widget-token", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ assessment_id: assessmentId }),
        });
        const body = (await res.json().catch(() => ({}))) as {
          widget_token?: string;
          detail?: string;
        };
        if (!res.ok) {
          throw new Error(
            body.detail || "Unable to prepare the SBAR viewer. Please retry.",
          );
        }
        if (!body.widget_token) {
          throw new Error("Widget token missing from server response.");
        }
        if (!cancelled) setToken(body.widget_token);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to prepare the SBAR viewer.",
          );
          setToken(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    if (assessmentId) void mint();
    return () => {
      cancelled = true;
    };
  }, [assessmentId]);

  useEffect(() => {
    let cancelled = false;
    async function loadAlerts() {
      if (!assessmentId) return;
      try {
        const meta = await fetchAssessmentMeta(assessmentId);
        if (!cancelled) {
          setComplianceAlerts(
            Array.isArray(meta.compliance_alerts) ? meta.compliance_alerts : [],
          );
          setRecallNeedsReview(Boolean(meta.recall_needs_review));
          setRecallMissingFlags(
            Array.isArray(meta.recall_exhaustion?.missing_flags)
              ? meta.recall_exhaustion?.missing_flags ?? []
              : [],
          );
        }
      } catch {
        if (!cancelled) {
          setComplianceAlerts([]);
          setRecallNeedsReview(false);
          setRecallMissingFlags([]);
        }
      }
    }
    void loadAlerts();
    return () => {
      cancelled = true;
    };
  }, [assessmentId]);

  async function handleDownloadPdf() {
    if (!assessmentId || exporting) return;
    setExporting(true);
    setExportError(null);
    try {
      const assessment = await fetchAssessmentForPdf(assessmentId);
      const markdown = composeSbarMarkdownFromAssessment(assessment);
      await exportSbarPdf(markdown, { assessmentId });
    } catch (err) {
      setExportError(
        err instanceof Error
          ? err.message
          : "Unable to create the PDF. Please retry.",
      );
    } finally {
      setExporting(false);
    }
  }

  if (!assessmentId) {
    return (
      <Alert severity="warning" data-testid={`${testId}-missing-id`}>
        No assessment id is available for this SBAR.
      </Alert>
    );
  }

  const proxyOrigin =
    typeof window !== "undefined" ? window.location.origin : "";
  const bootstrapping = loading || Boolean(token && !widgetReady);

  return (
    <Box data-testid={testId}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        justifyContent="flex-end"
        sx={{ mb: 1 }}
      >
        <Button
          size="small"
          variant="outlined"
          startIcon={
            exporting ? (
              <CircularProgress size={14} aria-label="Preparing PDF" />
            ) : (
              <PictureAsPdfIcon fontSize="small" />
            )
          }
          onClick={() => void handleDownloadPdf()}
          disabled={exporting}
          aria-label="Download SBAR as PDF"
          data-testid="leo-sbar-download-pdf"
        >
          {exporting ? "Preparing PDF" : "Download PDF"}
        </Button>
      </Stack>

      {exportError && (
        <Alert
          severity="error"
          sx={{ mb: 1 }}
          data-testid="leo-sbar-download-pdf-error"
        >
          {exportError}
        </Alert>
      )}

      {recallNeedsReview && (
        <Alert severity="warning" sx={{ mb: 1 }} data-testid="leo-sbar-recall-alert">
          Referral reason recall did not finish within the pinned budget.
          {recallMissingFlags.length > 0
            ? ` Flags: ${recallMissingFlags.join(", ")}.`
            : " A reviewer should check the Situation section."}
        </Alert>
      )}

      {complianceAlerts.map((item, index) => (
        <Alert
          key={`${item.alert_type || "alert"}-${index}`}
          severity="warning"
          sx={{ mb: 1 }}
          data-testid="leo-sbar-compliance-alert"
        >
          {item.message ||
            "Structured referral priority may not match the letter wording."}
        </Alert>
      ))}

      {bootstrapping && !error && (
        <Box sx={{ p: 2 }} data-testid="leo-sbar-loading">
          <LeoLoader
            layout="inline"
            size="sm"
            variant="light"
            label="Loading SBAR viewer..."
          />
        </Box>
      )}

      {!bootstrapping && widgetReady && token && (
        <leo-sbar
          data-testid="leo-sbar-widget"
          assessment-id={assessmentId}
          widget-token={token}
          proxy-origin={proxyOrigin}
        />
      )}

      {!bootstrapping && (error || !token) && (
        <Alert severity="error" data-testid={`${testId}-error`}>
          {error || "Unable to load SBAR viewer."}
        </Alert>
      )}
    </Box>
  );
}
