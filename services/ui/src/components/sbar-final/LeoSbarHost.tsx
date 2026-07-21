"use client";

/**
 * CDN / workspace host for the clinical leo-sbar widget.
 *
 * Atlas: DI-A898556B / DO-158BE606
 */

import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

import "@mizaic/leo-widget";

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

export function LeoSbarHost({
  assessmentId,
  testId = "leo-sbar-host",
}: LeoSbarHostProps) {
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  if (!assessmentId) {
    return (
      <Alert severity="warning" data-testid={`${testId}-missing-id`}>
        No assessment id is available for this SBAR.
      </Alert>
    );
  }

  if (loading) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 2 }}>
        <CircularProgress size={20} aria-label="Loading SBAR widget" />
        <Typography variant="body2">Loading SBAR viewer...</Typography>
      </Box>
    );
  }

  if (error || !token) {
    return (
      <Alert severity="error" data-testid={`${testId}-error`}>
        {error || "Unable to load SBAR viewer."}
      </Alert>
    );
  }

  const proxyOrigin =
    typeof window !== "undefined" ? window.location.origin : "";

  return (
    <Box data-testid={testId}>
      <leo-sbar
        data-testid="leo-sbar-widget"
        assessment-id={assessmentId}
        widget-token={token}
        proxy-origin={proxyOrigin}
      />
    </Box>
  );
}
