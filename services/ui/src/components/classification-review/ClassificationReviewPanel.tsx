"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import HowToVoteOutlinedIcon from "@mui/icons-material/HowToVoteOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import ClassificationValidationReport from "./ClassificationValidationReport";
import ClassificationPromptPanel from "./ClassificationPromptPanel";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DisagreementRecord {
  encounter_id: string;
  patient_id?: string;
  date: string | null;
  text: string | null;
  consensus_type: string;
  model_a_type: string;
  model_b_type: string;
  domains: string[] | null;
  clinical_significance: string | null;
  run_id: string | null;
  voted_type: string | null;
  reviewer: string | null;
  voted_at: string | null;
}

interface ScoreCard {
  model_a_label: string;
  model_b_label: string;
  model_a_correct: number;
  model_b_correct: number;
  both_wrong: number;
  total_votes: number;
  model_a_accuracy_pct: number;
  model_b_accuracy_pct: number;
}

type ContentType = "clinical" | "admin_only" | "document_transfer";

const CONTENT_TYPE_LABELS: Record<ContentType, string> = {
  clinical: "Clinical",
  admin_only: "Admin only",
  document_transfer: "Document transfer",
};

const CONTENT_TYPE_COLORS: Record<ContentType, "success" | "warning" | "info"> = {
  clinical: "success",
  admin_only: "warning",
  document_transfer: "info",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ContentTypeChip({ value }: { value: string }) {
  const label = CONTENT_TYPE_LABELS[value as ContentType] ?? value;
  const color = CONTENT_TYPE_COLORS[value as ContentType] ?? "default";
  return <Chip label={label} color={color} size="small" sx={{ fontWeight: 600 }} />;
}

function ScoreBar({ label, correct, total }: { label: string; correct: number; total: number }) {
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
  return (
    <Box sx={{ flex: 1 }}>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.8rem" }}>
          {label}
        </Typography>
        <Typography variant="body2" sx={{ color: pct >= 70 ? "success.main" : "warning.main", fontWeight: 700 }}>
          {pct}%
        </Typography>
      </Stack>
      <Box sx={{ height: 8, borderRadius: 4, bgcolor: "action.hover", overflow: "hidden" }}>
        <Box
          sx={{
            height: "100%",
            width: `${pct}%`,
            bgcolor: pct >= 70 ? "success.main" : "warning.main",
            borderRadius: 4,
            transition: "width 0.5s ease",
          }}
        />
      </Box>
      <Typography variant="caption" color="text.secondary">
        {correct} / {total} correct
      </Typography>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function ClassificationReviewPanel() {
  const { session } = useAuth();
  const reviewer = session?.user?.name ?? session?.user?.email ?? "unknown";

  const [patientId, setPatientId] = useState("");
  const [records, setRecords] = useState<DisagreementRecord[]>([]);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [scorecard, setScorecard] = useState<ScoreCard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState<Record<string, boolean>>({});
  // store the voted type per card so reviewed cards display correctly after quick-vote
  const [votes, setVotes] = useState<Record<string, ContentType>>({});

  const loadScorecard = useCallback(async () => {
    try {
      const data = await api.get<ScoreCard>("/pipeline/classification-scorecard");
      setScorecard(data);
    } catch {
      // non-critical
    }
  }, []);

  const loadDisagreements = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = patientId.trim() ? `?patient_id=${patientId.trim()}` : "?limit=100";
      const data = await api.get<{
        disagreements: DisagreementRecord[];
        pending_review: number;
      }>(`/pipeline/classification-disagreements${params}`);
      setRecords(data.disagreements);
      setPendingCount(data.pending_review);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load disagreements");
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    loadDisagreements();
    loadScorecard();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function submitVote(record: DisagreementRecord, correctType: ContentType, noteText = "") {
    setSubmitting((s) => ({ ...s, [record.encounter_id]: true }));
    try {
      await api.post("/pipeline/classification-vote", {
        encounter_id: record.encounter_id,
        correct_type: correctType,
        model_a_type: record.model_a_type,
        model_b_type: record.model_b_type,
        notes: noteText,
        reviewer,
      });
      setVotes((v) => ({ ...v, [record.encounter_id]: correctType }));
      setSubmitted((s) => ({ ...s, [record.encounter_id]: true }));
      loadScorecard();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit vote");
    } finally {
      setSubmitting((s) => ({ ...s, [record.encounter_id]: false }));
    }
  }

  const pendingRecords = records.filter((r) => !r.voted_type && !submitted[r.encounter_id]);
  const reviewedRecords = records.filter((r) => r.voted_type || submitted[r.encounter_id]);

  return (
    <Box sx={{ maxWidth: 960, mx: "auto", py: 4, px: 3 }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            Classification Review
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Encounters where Haiku and GPT-5-mini disagreed. Your vote corrects the label and improves future prompts.
          </Typography>
        </Box>
        {pendingCount !== null && (
          <Chip
            icon={<HowToVoteOutlinedIcon />}
            label={`${pendingCount} awaiting review`}
            color={pendingCount > 0 ? "warning" : "success"}
            sx={{ fontWeight: 600 }}
          />
        )}
      </Stack>

      {/* Scorecard */}
      {scorecard && scorecard.total_votes > 0 && (
        <Card sx={{ mb: 3, bgcolor: "action.hover" }}>
          <CardContent>
            <Stack direction="row" alignItems="center" gap={1} sx={{ mb: 2 }}>
              <BarChartOutlinedIcon sx={{ color: "text.secondary" }} />
              <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
                Model Scorecard — {scorecard.total_votes} votes cast
              </Typography>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={3}>
              <ScoreBar
                label={scorecard.model_a_label}
                correct={scorecard.model_a_correct}
                total={scorecard.total_votes}
              />
              <ScoreBar
                label={scorecard.model_b_label}
                correct={scorecard.model_b_correct}
                total={scorecard.total_votes}
              />
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.8rem", mb: 0.5 }}>
                  Both wrong
                </Typography>
                <Typography variant="body1" sx={{ fontWeight: 700, color: "error.main" }}>
                  {scorecard.both_wrong}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  encounters
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Filter */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={2} alignItems="flex-end">
            <TextField
              label="Patient ID (leave blank for all)"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              size="small"
              sx={{ flex: 1 }}
              InputProps={{ sx: { fontFamily: "var(--font-mono)" } }}
            />
            <Button variant="contained" onClick={loadDisagreements} disabled={loading}>
              {loading ? <CircularProgress size={18} /> : "Load"}
            </Button>
          </Stack>
        </CardContent>
      </Card>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Pending */}
      {pendingRecords.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>
            Awaiting your vote ({pendingRecords.length})
          </Typography>
          <Stack spacing={2}>
            {pendingRecords.map((record) => (
              <DisagreementCard
                key={record.encounter_id}
                record={record}
                submitting={!!submitting[record.encounter_id]}
                onSubmit={(type, note) => submitVote(record, type, note)}
              />
            ))}
          </Stack>
        </Box>
      )}

      {/* Already reviewed */}
      {reviewedRecords.length > 0 && (
        <Box>
          <Divider sx={{ mb: 3 }} />
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2, color: "text.secondary" }}>
            Already reviewed ({reviewedRecords.length})
          </Typography>
          <Stack spacing={1.5}>
            {reviewedRecords.map((record) => (
              <ReviewedCard key={record.encounter_id} record={record} submitted={submitted[record.encounter_id]} votes={votes} />
            ))}
          </Stack>
        </Box>
      )}

      {!loading && records.length === 0 && (
        <Box sx={{ textAlign: "center", py: 8 }}>
          <CheckCircleOutlineIcon sx={{ fontSize: 48, color: "success.main", mb: 1 }} />
          <Typography variant="h6" color="text.secondary">
            No disagreements found
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Run the pipeline on some patients first, or broaden your filter.
          </Typography>
        </Box>
      )}

      {/* Prompt improvement — shows live few-shot status */}
      <ClassificationPromptPanel />

      {/* Validation evidence report — always available */}
      <ClassificationValidationReport />
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Disagreement card (pending vote)
// ---------------------------------------------------------------------------

function DisagreementCard({
  record,
  submitting,
  onSubmit,
}: {
  record: DisagreementRecord;
  submitting: boolean;
  onSubmit: (type: ContentType, note: string) => void;
}) {
  const [neitherOpen, setNeitherOpen] = useState(false);
  const [neitherType, setNeitherType] = useState<ContentType | "">("");
  const [neitherNote, setNeitherNote] = useState("");

  function handleQuickVote(type: ContentType) {
    onSubmit(type, "");
  }

  function handleNeitherSubmit() {
    if (!neitherType) return;
    onSubmit(neitherType as ContentType, neitherNote);
  }

  const modelAColor = CONTENT_TYPE_COLORS[record.model_a_type as ContentType] ?? "default";
  const modelBColor = CONTENT_TYPE_COLORS[record.model_b_type as ContentType] ?? "default";

  const btnSx = {
    textTransform: "none",
    fontWeight: 600,
    px: 2,
    py: 0.75,
    borderRadius: 2,
    fontSize: "0.82rem",
  } as const;

  return (
    <Card variant="outlined" sx={{ borderColor: "warning.main", borderWidth: 1.5 }}>
      <CardContent>
        {/* Header row */}
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} justifyContent="space-between" sx={{ mb: 1.5 }}>
          <Box>
            {record.date && (
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "var(--font-mono)" }}>
                {record.date}
              </Typography>
            )}
            {record.patient_id && (
              <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5, fontFamily: "var(--font-mono)" }}>
                Patient {record.patient_id}
              </Typography>
            )}
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Tooltip title="Claude Haiku said:">
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>Haiku:</Typography>
                <ContentTypeChip value={record.model_a_type} />
              </Box>
            </Tooltip>
            <Typography variant="caption" color="text.secondary">vs</Typography>
            <Tooltip title="GPT-5-mini said:">
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>GPT-5-mini:</Typography>
                <ContentTypeChip value={record.model_b_type} />
              </Box>
            </Tooltip>
          </Stack>
        </Stack>

        {/* Encounter text */}
        <Box
          sx={{
            p: 1.5,
            bgcolor: "action.hover",
            borderRadius: 1,
            mb: 2,
            maxHeight: 140,
            overflowY: "auto",
            fontFamily: "var(--font-mono)",
            fontSize: "0.8rem",
            lineHeight: 1.6,
            color: "text.primary",
            whiteSpace: "pre-wrap",
          }}
        >
          {record.text ?? "(no text)"}
        </Box>

        {/* Quick-vote row */}
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
            Correct answer:
          </Typography>
          <Tooltip title={`Haiku was right — ${CONTENT_TYPE_LABELS[record.model_a_type as ContentType] ?? record.model_a_type}`}>
            <span>
              <Button
                variant="contained"
                color={modelAColor}
                size="small"
                disabled={submitting}
                onClick={() => handleQuickVote(record.model_a_type as ContentType)}
                sx={btnSx}
              >
                {submitting ? <CircularProgress size={14} /> : `Haiku · ${CONTENT_TYPE_LABELS[record.model_a_type as ContentType] ?? record.model_a_type}`}
              </Button>
            </span>
          </Tooltip>
          <Tooltip title={`GPT-5-mini was right — ${CONTENT_TYPE_LABELS[record.model_b_type as ContentType] ?? record.model_b_type}`}>
            <span>
              <Button
                variant="contained"
                color={modelBColor}
                size="small"
                disabled={submitting}
                onClick={() => handleQuickVote(record.model_b_type as ContentType)}
                sx={btnSx}
              >
                {submitting ? <CircularProgress size={14} /> : `GPT-5-mini · ${CONTENT_TYPE_LABELS[record.model_b_type as ContentType] ?? record.model_b_type}`}
              </Button>
            </span>
          </Tooltip>
          <Tooltip title="Neither model was right — choose the correct label">
            <Button
              variant="outlined"
              color="inherit"
              size="small"
              disabled={submitting}
              onClick={() => setNeitherOpen((o) => !o)}
              endIcon={<ExpandMoreIcon sx={{ transform: neitherOpen ? "rotate(180deg)" : "none", transition: "transform 0.2s" }} />}
              sx={{ ...btnSx, borderColor: "divider" }}
            >
              Neither
            </Button>
          </Tooltip>
        </Stack>

        {/* Neither — inline picker */}
        <Collapse in={neitherOpen} unmountOnExit>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems={{ sm: "flex-end" }} sx={{ mt: 2, pt: 2, borderTop: "1px solid", borderColor: "divider" }}>
            <Select
              value={neitherType}
              onChange={(e) => setNeitherType(e.target.value as ContentType)}
              displayEmpty
              size="small"
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="" disabled>Choose correct label</MenuItem>
              <MenuItem value="clinical">Clinical</MenuItem>
              <MenuItem value="admin_only">Admin only</MenuItem>
              <MenuItem value="document_transfer">Document transfer</MenuItem>
            </Select>
            <TextField
              label="Notes (optional)"
              value={neitherNote}
              onChange={(e) => setNeitherNote(e.target.value)}
              size="small"
              sx={{ flex: 1 }}
              placeholder="e.g. clearly admin, neither model correct"
            />
            <Button
              variant="contained"
              color="primary"
              size="small"
              onClick={handleNeitherSubmit}
              disabled={!neitherType || submitting}
              startIcon={submitting ? <CircularProgress size={14} /> : <HowToVoteOutlinedIcon />}
              sx={{ whiteSpace: "nowrap" }}
            >
              Submit
            </Button>
          </Stack>
        </Collapse>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Reviewed card (already has a vote)
// ---------------------------------------------------------------------------

function ReviewedCard({
  record,
  submitted,
  votes,
}: {
  record: DisagreementRecord;
  submitted: boolean;
  votes: Record<string, ContentType>;
}) {
  const correctType = submitted ? votes[record.encounter_id] : (record.voted_type ?? "");
  const reviewer = record.reviewer ?? "you";

  return (
    <Card variant="outlined" sx={{ opacity: 0.75 }}>
      <CardContent sx={{ py: "12px !important" }}>
        <Stack direction="row" spacing={2} alignItems="center" justifyContent="space-between" flexWrap="wrap">
          <Stack direction="row" spacing={1} alignItems="center">
            <CheckCircleOutlineIcon sx={{ color: "success.main", fontSize: 18 }} />
            <Typography variant="body2" sx={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem", color: "text.secondary" }}>
              {record.date ?? ""}
            </Typography>
            {record.patient_id && (
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "var(--font-mono)" }}>
                Patient {record.patient_id}
              </Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" color="text.secondary">Haiku:</Typography>
            <ContentTypeChip value={record.model_a_type} />
            <Typography variant="caption" color="text.secondary">GPT-5-mini:</Typography>
            <ContentTypeChip value={record.model_b_type} />
            <Typography variant="caption" sx={{ fontWeight: 700, color: "primary.main" }}>
              Correct:
            </Typography>
            {correctType && <ContentTypeChip value={correctType} />}
            <Typography variant="caption" color="text.secondary">
              by {reviewer}
            </Typography>
          </Stack>
        </Stack>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
        >
          {record.text ?? ""}
        </Typography>
      </CardContent>
    </Card>
  );
}
