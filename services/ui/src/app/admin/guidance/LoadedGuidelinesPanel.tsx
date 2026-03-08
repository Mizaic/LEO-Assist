"use client";

/**
 * Panel showing all NICE guidelines currently loaded into the Neo4j knowledge graph.
 *
 * For each guideline the panel shows:
 *   - Code chip and full title
 *   - Chapter count and recommendation count (from the hierarchical graph)
 *   - Rule status badge: No rules / X pending review / X approved / mixed
 *   - "Generate rules" button to trigger the LLM pipeline
 *
 * Reading age 11 copy. No silent errors.
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import RefreshIcon from "@mui/icons-material/Refresh";
import ConfirmDialog from "@/components/ConfirmDialog";
import GuidelineSubgraphDrawer from "./GuidelineSubgraphDrawer";

interface LoadedGuideline {
  code: string;
  title: string;
  guidance_type: string;
  publication_date: string;
  chapter_count: number;
  recommendation_count: number;
  rules_pending: number;
  rules_approved: number;
  rules_rejected: number;
}

interface Props {
  /** Increment to force a refresh from the parent (e.g. after a new ingest). */
  refreshKey?: number;
  /** Called after rule generation completes so the rule review section can refresh. */
  onRulesGenerated?: () => void;
}

function ruleStatusChip(g: LoadedGuideline) {
  const total = g.rules_pending + g.rules_approved + g.rules_rejected;
  if (total === 0) {
    return <Chip label="No rules yet" size="small" variant="outlined" color="default" />;
  }
  if (g.rules_pending > 0 && g.rules_approved === 0) {
    return (
      <Chip
        label={`${g.rules_pending} to review`}
        size="small"
        color="warning"
        variant="outlined"
      />
    );
  }
  if (g.rules_approved > 0 && g.rules_pending === 0) {
    return (
      <Chip
        label={`${g.rules_approved} approved`}
        size="small"
        color="success"
        variant="outlined"
      />
    );
  }
  // Mix of pending and approved
  return (
    <Stack direction="row" spacing={0.5}>
      <Chip label={`${g.rules_pending} pending`} size="small" color="warning" variant="outlined" />
      <Chip label={`${g.rules_approved} approved`} size="small" color="success" variant="outlined" />
    </Stack>
  );
}

export default function LoadedGuidelinesPanel({ refreshKey, onRulesGenerated }: Props) {
  const [guidelines, setGuidelines] = useState<LoadedGuideline[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Per-guideline generation state
  const [generating, setGenerating] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState<string | null>(null);

  // Subgraph inspect drawer
  const [inspectCode, setInspectCode] = useState<string | null>(null);

  const fetchLoaded = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/nice/loaded");
      if (!r.ok) throw new Error(r.statusText);
      setGuidelines(await r.json());
    } catch {
      setError("Could not load the list of guidelines. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLoaded();
  }, [fetchLoaded, refreshKey]);

  const handleGenerate = useCallback(
    async (code: string) => {
      setConfirmCode(null);
      setGenerating(code);
      setGenerateError(null);
      try {
        const r = await fetch("/api/guidance/rules/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ guideline_id: code }),
        });
        if (!r.ok) {
          const detail = await r.json().catch(() => ({ detail: r.statusText }));
          throw new Error(detail.detail || r.statusText);
        }
        // Refresh counts once generation kicks off (it runs in background)
        await fetchLoaded();
        onRulesGenerated?.();
      } catch (e) {
        setGenerateError(
          e instanceof Error ? e.message : "Could not start rule generation. Please try again."
        );
      } finally {
        setGenerating(null);
      }
    },
    [fetchLoaded, onRulesGenerated]
  );

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
        <CircularProgress size={24} aria-label="Loading loaded guidelines" />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (guidelines.length === 0) {
    return (
      <Typography color="text.secondary" sx={{ py: 1 }}>
        No guidelines loaded yet. Use the search above to find and load a guideline.
      </Typography>
    );
  }

  return (
    <Box>
      {generateError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setGenerateError(null)}>
          {generateError}
        </Alert>
      )}

      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="body2" color="text.secondary">
          {guidelines.length} guideline{guidelines.length !== 1 ? "s" : ""} in the knowledge graph
        </Typography>
        <Tooltip title="Refresh list">
          <IconButton size="small" onClick={fetchLoaded} aria-label="Refresh loaded guidelines list">
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>

      <Divider sx={{ mb: 1 }} />

      <Table size="small" aria-label="Loaded guidelines">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 700 }}>Code</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Guideline</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="center">Chapters</TableCell>
            <TableCell sx={{ fontWeight: 700 }} align="center">Recommendations</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Rule status</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Actions</TableCell>
            <TableCell sx={{ fontWeight: 700 }}>Inspect</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {guidelines.map((g) => {
            const hasRules = g.rules_pending + g.rules_approved + g.rules_rejected > 0;
            const isGenerating = generating === g.code;
            return (
              <TableRow key={g.code} hover>
                <TableCell>
                  <Chip label={g.code} size="small" color="primary" variant="outlined" />
                </TableCell>
                <TableCell>
                  <Typography variant="body2" sx={{ fontWeight: 500 }}>
                    {g.title || g.code}
                  </Typography>
                  {g.guidance_type && (
                    <Typography variant="caption" color="text.secondary">
                      {g.guidance_type}
                    </Typography>
                  )}
                </TableCell>
                <TableCell align="center">
                  <Typography variant="body2">{g.chapter_count}</Typography>
                </TableCell>
                <TableCell align="center">
                  <Typography variant="body2">{g.recommendation_count}</Typography>
                </TableCell>
                <TableCell>{ruleStatusChip(g)}</TableCell>
                <TableCell>
                  <Tooltip
                    title={
                      hasRules
                        ? "Re-generate rules (will replace existing draft rules)"
                        : "Ask the AI to write rules for each recommendation"
                    }
                  >
                    <span>
                      <Button
                        size="small"
                        variant={hasRules ? "outlined" : "contained"}
                        color={hasRules ? "warning" : "primary"}
                        disabled={isGenerating || g.recommendation_count === 0}
                        startIcon={
                          isGenerating ? (
                            <CircularProgress size={14} color="inherit" />
                          ) : (
                            <AutoFixHighOutlinedIcon fontSize="small" />
                          )
                        }
                        onClick={() =>
                          hasRules ? setConfirmCode(g.code) : handleGenerate(g.code)
                        }
                        aria-label={`Generate rules for ${g.code}`}
                      >
                        {isGenerating
                          ? "Generating\u2026"
                          : hasRules
                          ? "Re-generate"
                          : "Generate rules"}
                      </Button>
                    </span>
                  </Tooltip>
                </TableCell>
                <TableCell>
                  <Tooltip title="Inspect what is stored in Neo4j for this guideline">
                    <IconButton
                      size="small"
                      onClick={() => setInspectCode(g.code)}
                      aria-label={`Inspect Neo4j subgraph for ${g.code}`}
                      color={g.recommendation_count === 0 ? "error" : "default"}
                    >
                      <AccountTreeIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {confirmCode && (
        <ConfirmDialog
          title="Replace existing rules?"
          body={`This will delete all draft rules for ${confirmCode} and ask the AI to write new ones. Rules you have already approved will also be deleted. Are you sure?`}
          confirmLabel="Yes, re-generate"
          cancelLabel="Cancel"
          variant="warning"
          onConfirm={() => handleGenerate(confirmCode)}
          onCancel={() => setConfirmCode(null)}
        />
      )}

      <GuidelineSubgraphDrawer
        code={inspectCode}
        onClose={() => setInspectCode(null)}
      />
    </Box>
  );
}
