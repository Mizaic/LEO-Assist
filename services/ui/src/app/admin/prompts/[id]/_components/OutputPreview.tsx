/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Renders the expected JSON output of a few-shot example as labelled term
 * chips. Extracted from prompts/[id]/page.tsx (Phase 4b decomposition).
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { ASSERTION_COLORS, TAG_COLORS } from "./types";

interface OutputTerm {
  text?: string;
  lookup_term?: string | null;
  semantic_tag?: string | null;
  assertion?: string | null;
  value?: string | null;
  unit?: string | null;
  reference_range?: string | null;
}

export function OutputPreview({ outputJson }: { outputJson: string }) {
  if (!outputJson.trim()) {
    return (
      <Typography variant="body2" color="text.disabled" fontStyle="italic">
        No expected output yet
      </Typography>
    );
  }
  let terms: OutputTerm[] = [];
  let parseError = false;
  try {
    const data = JSON.parse(outputJson);
    terms = Array.isArray(data.terms) ? data.terms : [];
  } catch {
    parseError = true;
  }

  if (parseError) {
    return (
      <Alert severity="error" sx={{ py: 0.25, fontSize: "0.75rem" }}>
        Output JSON is invalid -- switch to Edit to fix it.
      </Alert>
    );
  }

  if (terms.length === 0) {
    return (
      <Box
        sx={{
          px: 1.5,
          py: 1,
          bgcolor: "grey.50",
          borderRadius: 1,
          border: "1px dashed",
          borderColor: "divider",
          display: "inline-flex",
          alignItems: "center",
        }}
      >
        <Typography variant="caption" color="text.secondary">
          No entities extracted -- correct for pure administrative text
        </Typography>
      </Box>
    );
  }

  return (
    <Stack spacing={0.5}>
      {terms.map((t, i) => (
        <Stack
          key={i}
          direction="row"
          alignItems="center"
          spacing={0.5}
          flexWrap="wrap"
          useFlexGap
          sx={{ p: 0.75, bgcolor: "grey.50", borderRadius: 1 }}
        >
          <Typography
            variant="body2"
            fontWeight={700}
            sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}
          >
            &ldquo;{t.text}&rdquo;
          </Typography>
          {t.lookup_term && t.lookup_term !== t.text && (
            <>
              <Typography
                variant="caption"
                color="text.disabled"
                sx={{ mx: 0.25 }}
              >
                {"->"}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                fontStyle="italic"
              >
                {t.lookup_term}
              </Typography>
            </>
          )}
          <Chip
            size="small"
            label={t.semantic_tag ?? "?"}
            color={TAG_COLORS[t.semantic_tag ?? ""] ?? "default"}
            sx={{ height: 18, fontSize: "0.62rem" }}
          />
          <Chip
            size="small"
            label={t.assertion ?? "?"}
            color={ASSERTION_COLORS[t.assertion ?? ""] ?? "default"}
            variant="outlined"
            sx={{ height: 18, fontSize: "0.62rem" }}
          />
          {(t.value || t.unit) && (
            <Chip
              size="small"
              label={[t.value, t.unit].filter(Boolean).join(" ")}
              sx={{
                height: 18,
                fontSize: "0.62rem",
                bgcolor: "primary.50",
                color: "primary.dark",
              }}
            />
          )}
          {t.reference_range && (
            <Chip
              size="small"
              label={`range: ${t.reference_range}`}
              variant="outlined"
              sx={{ height: 18, fontSize: "0.62rem" }}
            />
          )}
        </Stack>
      ))}
    </Stack>
  );
}
