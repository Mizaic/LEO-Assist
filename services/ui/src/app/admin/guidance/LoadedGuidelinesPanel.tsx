/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";

import { EmptyState, ReviewListCard, ToolbarActions, type ReviewListItem } from "@leo/design-system";
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
  refreshKey?: number;
  onRulesGenerated?: () => void;
}

function ruleStatusPill(g: LoadedGuideline): ReactNode {
  const total = g.rules_pending + g.rules_approved + g.rules_rejected;
  if (total === 0) return <Chip label="No rules yet" size="small" variant="outlined" />;
  const parts: string[] = [];
  if (g.rules_pending > 0) parts.push(`Pending (${g.rules_pending})`);
  if (g.rules_approved > 0) parts.push(`Approved (${g.rules_approved})`);
  if (parts.length === 0) return <Chip label="None approved" size="small" variant="outlined" />;
  return <Chip label={parts.join(" / ")} size="small" variant="outlined" />;
}

function buildGuidelineItem(
  g: LoadedGuideline,
  generating: string | null,
  onGenerate: (code: string, hasRules: boolean) => void,
  onInspect: (code: string) => void,
): ReviewListItem {
  const hasRules = g.rules_pending + g.rules_approved + g.rules_rejected > 0;
  const isGenerating = generating === g.code;

  return {
    id: g.code,
    tone: g.recommendation_count === 0 ? "danger" : "neutral",
    title: (
      <Stack direction="row" spacing={1} alignItems="center">
        <Chip label={g.code} size="small" sx={{ bgcolor: "#DBEAFE", color: "#1D4ED8", border: "1px solid #BFDBFE", fontWeight: 700 }} />
        <Typography variant="body2" sx={{ fontWeight: 500 }}>{g.title || g.code}</Typography>
      </Stack>
    ),
    meta: (
      <Stack direction="row" spacing={2}>
        <span>{g.chapter_count} chapters</span>
        <span>{g.recommendation_count} recommendations</span>
        {g.guidance_type && <span>{g.guidance_type}</span>}
      </Stack>
    ),
    chips: ruleStatusPill(g),
    actions: (
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Tooltip title={hasRules ? "Re-generate rules (replaces drafts)" : "Ask the AI to write rules for each recommendation"}>
          <span>
            <Button
              size="small"
              variant={hasRules ? "outlined" : "contained"}
              color={hasRules ? "warning" : "primary"}
              disabled={isGenerating || g.recommendation_count === 0}
              startIcon={isGenerating ? <CircularProgress size={14} color="inherit" /> : <AutoFixHighOutlinedIcon fontSize="small" />}
              onClick={() => onGenerate(g.code, hasRules)}
              aria-label={`Generate rules for ${g.code}`}
            >
              {isGenerating ? "Generating..." : hasRules ? "Re-generate" : "Generate rules"}
            </Button>
          </span>
        </Tooltip>
        <Tooltip title="Inspect what is stored in Neo4j for this guideline">
          <span>
            <Button size="small" variant="outlined" onClick={() => onInspect(g.code)} aria-label={`Inspect Neo4j subgraph for ${g.code}`}>
              <AccountTreeIcon fontSize="small" />
            </Button>
          </span>
        </Tooltip>
      </Stack>
    ),
  };
}

export default function LoadedGuidelinesPanel({ refreshKey, onRulesGenerated }: Props) {
  const [guidelines, setGuidelines] = useState<LoadedGuideline[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState<string | null>(null);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [confirmCode, setConfirmCode] = useState<string | null>(null);
  const [inspectCode, setInspectCode] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

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

  useEffect(() => { fetchLoaded(); }, [fetchLoaded, refreshKey]);

  const handleGenerate = useCallback(async (code: string) => {
    setConfirmCode(null);
    setGenerating(code);
    setGenerateError(null);
    if (pollRef.current) clearTimeout(pollRef.current);

    let jobId: string;
    try {
      const r = await fetch("/api/guidance/rules/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guideline_id: code, only_without_rules: true }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(body.detail || r.statusText);
      }
      jobId = (await r.json()).job_id;
    } catch (e) {
      setGenerateError(e instanceof Error ? e.message : "Could not start rule generation. Please try again.");
      setGenerating(null);
      return;
    }

    async function poll() {
      try {
        const r = await fetch(`/api/guidance/rules/generate/${jobId}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const job = await r.json();
        if (job.status === "done") { await fetchLoaded(); onRulesGenerated?.(); setGenerating(null); return; }
        if (job.status === "error") { setGenerateError(job.error || "Rule generation failed."); await fetchLoaded(); setGenerating(null); return; }
        pollRef.current = setTimeout(poll, 5000);
      } catch {
        setGenerateError("Lost contact with the server. Check the review queue to see if rules were created.");
        await fetchLoaded();
        onRulesGenerated?.();
        setGenerating(null);
      }
    }

    pollRef.current = setTimeout(poll, 3000);
  }, [fetchLoaded, onRulesGenerated]);

  if (loading) {
    return <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}><CircularProgress size={24} aria-label="Loading loaded guidelines" /></Box>;
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  return (
    <Box>
      {generateError && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setGenerateError(null)}>{generateError}</Alert>}

      {/* -- Toolbar -------------------------------------------------------- */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">
          {guidelines.length} guideline{guidelines.length !== 1 ? "s" : ""} in the knowledge graph
        </Typography>
        <ToolbarActions
          actions={[{ id: "refresh", label: "Refresh", variant: "ghost", onClick: fetchLoaded, icon: <RefreshIcon fontSize="small" />, loading }]}
        />
      </Stack>

      {/* -- List ----------------------------------------------------------- */}
      {guidelines.length === 0 ? (
        <EmptyState
          icon={<MenuBookOutlinedIcon fontSize="large" />}
          title="No guidelines loaded yet"
          body="Load a NICE guideline above to get started."
          data-testid="guidelines-empty"
        />
      ) : (
        <ReviewListCard
          items={guidelines.map((g) =>
            buildGuidelineItem(g, generating, (code, hasRules) => (hasRules ? setConfirmCode(code) : handleGenerate(code)), setInspectCode)
          )}
        />
      )}

      {confirmCode && (
        <ConfirmDialog
          title="Replace existing rules?"
          body={`This will delete all draft rules for ${confirmCode} and ask the AI to write new ones. Rules you have already approved will also be deleted. Are you sure?`}
          confirmLabel="Yes, re-generate"
          cancelLabel="Cancel"
          variant="danger"
          onConfirm={() => handleGenerate(confirmCode)}
          onCancel={() => setConfirmCode(null)}
        />
      )}

      <GuidelineSubgraphDrawer code={inspectCode} onClose={() => setInspectCode(null)} />
    </Box>
  );
}
