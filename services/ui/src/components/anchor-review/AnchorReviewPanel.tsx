"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Stack,
  Tab,
  Tabs,
  Typography,
} from "@mui/material";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import HowToVoteOutlinedIcon from "@mui/icons-material/HowToVoteOutlined";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import AnchorReviewCard from "./AnchorReviewCard";
import TabFlowDiagram, { type TabStage } from "@/components/operations/TabFlowDiagram";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AnchorReviewRecord {
  encounter_id: string;
  milestone_type: string;
  patient_id: string | null;
  original_label: number;
  text: string;
  original_concept_id: string | null;
  model_a_domain: string;
  model_a_concept_correct: boolean;
  model_a_assertion: string;
  model_a_rationale: string;
  model_a_target_rule: string;
  model_b_domain: string;
  model_b_concept_correct: boolean;
  model_b_assertion: string;
  model_b_rationale: string;
  model_b_target_rule: string;
  non_cancer_flag: boolean;
  voted_domain: string | null;
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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ScoreBar({
  label,
  correct,
  total,
}: {
  label: string;
  correct: number;
  total: number;
}) {
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0;
  return (
    <Box sx={{ flex: 1 }}>
      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.8rem" }}>
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            color: pct >= 70 ? "success.main" : "warning.main",
            fontWeight: 700,
          }}
        >
          {pct}%
        </Typography>
      </Stack>
      <Box
        sx={{
          height: 8,
          borderRadius: 4,
          bgcolor: "action.hover",
          overflow: "hidden",
        }}
      >
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
// How this tab works - stages for the flow diagram
// ---------------------------------------------------------------------------

const ANCHOR_STAGES: TabStage[] = [
  {
    id: "ar1", num: 1,
    label: "Two AIs Check It",
    tooltip: "Two AI tools read a note and decide which cancer care pathway it belongs to -- for example, a new referral, a diagnosis, or a follow-up.",
    detailIn: "A patient note that the anchor detector has flagged",
    detailOut: "Two cancer pathway labels -- one from each AI",
  },
  {
    id: "ar2", num: 2,
    label: "They Disagree",
    tooltip: "The two AIs give different pathway labels, or one says the note has nothing to do with cancer when we think it does.",
    detailIn: "Two different pathway labels for the same note",
    detailOut: "A disagreement record added to this review queue",
    branches: [
      {
        label: "NON_CANCER flag",
        description: "If the note was already flagged as cancer-related but one AI says NON_CANCER, it appears in the separate NON_CANCER flags tab as a precision warning",
      },
    ],
  },
  {
    id: "ar3", num: 3,
    label: "You See Both",
    tooltip: "You can read the full note and see both AI answers, with the reason each AI gave for its choice.",
    detailIn: "The note text, both pathway labels, and both reasons",
    detailOut: "A clear picture of the disagreement",
  },
  {
    id: "ar4", num: 4,
    label: "You Decide",
    tooltip: "You pick the correct cancer pathway domain from a list of options. Your vote is the ground truth.",
    detailIn: "Your clinical knowledge of the note",
    detailOut: "A vote with the correct pathway domain",
    branches: [
      {
        label: "Neither was right",
        description: "You can select a different domain from the full list if both AI labels were wrong",
      },
    ],
  },
  {
    id: "ar5", num: 5,
    label: "Domain Confirmed",
    tooltip: "Your answer is saved and linked to that note. It feeds into the AI training data to improve future pathway labelling.",
    detailIn: "Your voted domain",
    detailOut: "The correct pathway domain saved; AI scorecard updates",
  },
];

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function AnchorReviewPanel() {
  const { session } = useAuth();
  const reviewer =
    session?.user?.name ?? session?.user?.email ?? "unknown";

  const [tab, setTab] = useState<"disagreements" | "non_cancer">(
    "disagreements"
  );
  const [disagreements, setDisagreements] = useState<AnchorReviewRecord[]>([]);
  const [nonCancerFlags, setNonCancerFlags] = useState<AnchorReviewRecord[]>(
    []
  );
  const [pendingDisagreements, setPendingDisagreements] = useState<
    number | null
  >(null);
  const [pendingNonCancer, setPendingNonCancer] = useState<number | null>(null);
  const [scorecard, setScorecard] = useState<ScoreCard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Per-card vote state
  const [submitting, setSubmitting] = useState<Record<string, boolean>>({});
  const [submitted, setSubmitted] = useState<Record<string, boolean>>({});
  const [votes, setVotes] = useState<Record<string, string>>({});

  const loadScorecard = useCallback(async () => {
    try {
      const data = await api.get<ScoreCard>("/anchor-review/scorecard");
      setScorecard(data);
    } catch {
      // non-critical
    }
  }, []);

  const loadDisagreements = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<{
        disagreements: AnchorReviewRecord[];
        pending_review: number;
      }>("/anchor-review/disagreements?limit=200");
      setDisagreements(data.disagreements);
      setPendingDisagreements(data.pending_review);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to load disagreements"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadNonCancerFlags = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<{
        non_cancer_flags: AnchorReviewRecord[];
        pending_review: number;
      }>("/anchor-review/non-cancer?limit=200");
      setNonCancerFlags(data.non_cancer_flags);
      setPendingNonCancer(data.pending_review);
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Failed to load NON_CANCER flags"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDisagreements();
    loadNonCancerFlags();
    loadScorecard();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function submitVote(
    record: AnchorReviewRecord,
    correctDomain: string,
    notes = ""
  ) {
    const key = `${record.encounter_id}|${record.milestone_type}`;
    setSubmitting((s) => ({ ...s, [key]: true }));
    try {
      await api.post("/anchor-review/vote", {
        encounter_id: record.encounter_id,
        milestone_type: record.milestone_type,
        correct_domain: correctDomain,
        model_a_domain: record.model_a_domain,
        model_b_domain: record.model_b_domain,
        notes,
        reviewer,
      });
      setVotes((v) => ({ ...v, [key]: correctDomain }));
      setSubmitted((s) => ({ ...s, [key]: true }));
      loadScorecard();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit vote");
    } finally {
      setSubmitting((s) => ({ ...s, [key]: false }));
    }
  }

  const activeRecords =
    tab === "disagreements" ? disagreements : nonCancerFlags;
  const pendingCount =
    tab === "disagreements" ? pendingDisagreements : pendingNonCancer;

  const pendingRecords = activeRecords.filter((r) => {
    const key = `${r.encounter_id}|${r.milestone_type}`;
    return !r.voted_domain && !submitted[key];
  });
  const reviewedRecords = activeRecords.filter((r) => {
    const key = `${r.encounter_id}|${r.milestone_type}`;
    return r.voted_domain || submitted[key];
  });

  return (
    <Box sx={{ maxWidth: 1040, mx: "auto", py: 4, px: 3 }}>
      {/* How this works */}
      <Accordion variant="outlined" disableGutters sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            How this tab works
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pt: 0 }}>
          <TabFlowDiagram
            stages={ANCHOR_STAGES}
            color="#EF4444"
            lightColor="#FEF2F2"
            trackLabel="Anchor Review"
          />
        </AccordionDetails>
      </Accordion>

      {/* Header */}
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 3 }}
      >
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            Anchor Domain Review
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            Dual-model agreement review of cancer pathway anchor detections.
            Your votes improve label quality and TargetRule generation.
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
                Model Scorecard — {scorecard.total_votes} domain votes cast
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
                <Typography
                  variant="body2"
                  sx={{ fontWeight: 600, fontSize: "0.8rem", mb: 0.5 }}
                >
                  Both wrong
                </Typography>
                <Typography
                  variant="body1"
                  sx={{ fontWeight: 700, color: "error.main" }}
                >
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

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab
            value="disagreements"
            label={
              <Stack direction="row" spacing={1} alignItems="center">
                <span>Disagreements</span>
                {pendingDisagreements !== null && pendingDisagreements > 0 && (
                  <Badge
                    badgeContent={pendingDisagreements}
                    color="warning"
                    max={999}
                  />
                )}
              </Stack>
            }
          />
          <Tab
            value="non_cancer"
            label={
              <Stack direction="row" spacing={1} alignItems="center">
                <WarningAmberIcon sx={{ fontSize: 16, color: "error.main" }} />
                <span>NON_CANCER flags</span>
                {pendingNonCancer !== null && pendingNonCancer > 0 && (
                  <Badge
                    badgeContent={pendingNonCancer}
                    color="error"
                    max={999}
                  />
                )}
              </Stack>
            }
          />
        </Tabs>
      </Box>

      {tab === "non_cancer" && (
        <Alert severity="error" sx={{ mb: 3 }}>
          These records were labelled positive (label=1) by the anchor detector
          but one or both models assigned <strong>NON_CANCER</strong>. This
          indicates the upstream detector is leaking non-cancer events into the
          cancer pathway — a precision problem that will erode clinical trust.
          Review and vote to confirm or correct each one.
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      )}

      {/* Pending review */}
      {!loading && pendingRecords.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 2 }}>
            Awaiting your vote ({pendingRecords.length})
          </Typography>
          <Stack spacing={2}>
            {pendingRecords.map((record) => {
              const key = `${record.encounter_id}|${record.milestone_type}`;
              return (
                <AnchorReviewCard
                  key={key}
                  record={record}
                  submitting={!!submitting[key]}
                  onVote={(domain, note) => submitVote(record, domain, note)}
                />
              );
            })}
          </Stack>
        </Box>
      )}

      {/* Already reviewed */}
      {!loading && reviewedRecords.length > 0 && (
        <Box>
          <Divider sx={{ mb: 3 }} />
          <Typography
            variant="subtitle1"
            sx={{ fontWeight: 700, mb: 2, color: "text.secondary" }}
          >
            Already reviewed ({reviewedRecords.length})
          </Typography>
          <Stack spacing={1.5}>
            {reviewedRecords.map((record) => {
              const key = `${record.encounter_id}|${record.milestone_type}`;
              const votedDomain = submitted[key] ? votes[key] : record.voted_domain ?? "";
              return (
                <Card key={key} variant="outlined" sx={{ opacity: 0.72 }}>
                  <CardContent sx={{ py: "10px !important" }}>
                    <Stack
                      direction="row"
                      spacing={2}
                      alignItems="center"
                      justifyContent="space-between"
                      flexWrap="wrap"
                    >
                      <Stack direction="row" spacing={1} alignItems="center">
                        <CheckCircleOutlineIcon
                          sx={{ color: "success.main", fontSize: 18 }}
                        />
                        <Chip
                          label={record.milestone_type}
                          size="small"
                          variant="outlined"
                        />
                        {record.patient_id && (
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ fontFamily: "var(--font-mono)" }}
                          >
                            Patient {record.patient_id}
                          </Typography>
                        )}
                      </Stack>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography
                          variant="caption"
                          color="text.secondary"
                        >
                          Haiku:
                        </Typography>
                        <DomainChip domain={record.model_a_domain} />
                        <Typography
                          variant="caption"
                          color="text.secondary"
                        >
                          GPT:
                        </Typography>
                        <DomainChip domain={record.model_b_domain} />
                        <Typography
                          variant="caption"
                          sx={{ fontWeight: 700, color: "primary.main" }}
                        >
                          Correct:
                        </Typography>
                        {votedDomain && (
                          <DomainChip domain={votedDomain} />
                        )}
                      </Stack>
                    </Stack>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        display: "block",
                        mt: 0.5,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        fontFamily: "var(--font-mono)",
                      }}
                    >
                      {record.text}
                    </Typography>
                  </CardContent>
                </Card>
              );
            })}
          </Stack>
        </Box>
      )}

      {!loading && activeRecords.length === 0 && (
        <Box sx={{ textAlign: "center", py: 8 }}>
          <CheckCircleOutlineIcon
            sx={{ fontSize: 48, color: "success.main", mb: 1 }}
          />
          <Typography variant="h6" color="text.secondary">
            {tab === "disagreements"
              ? "No disagreements found"
              : "No NON_CANCER flags found"}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Run scripts/review_anchor_training.py first to populate this view.
          </Typography>
        </Box>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Shared domain chip
// ---------------------------------------------------------------------------

const DOMAIN_COLORS: Record<
  string,
  | "default"
  | "primary"
  | "secondary"
  | "error"
  | "info"
  | "success"
  | "warning"
> = {
  CANCER_DIAGNOSIS: "error",
  CANCER_DIAGNOSIS_EXCLUDED: "success",
  "2WW_REFERRAL": "primary",
  "2WW_CLINIC_SEEN": "info",
  "2WW_REFERRAL_REJECTED": "warning",
  CANCER_TREATMENT: "secondary",
  CANCER_TREATMENT_HISTORICAL: "default",
  INVESTIGATION: "info",
  METASTATIC_DISEASE: "error",
  NON_CANCER: "warning",
  DISAGREEMENT: "warning",
  AMBIGUOUS: "default",
};

export function DomainChip({ domain }: { domain: string }) {
  const color = DOMAIN_COLORS[domain] ?? "default";
  return (
    <Chip
      label={domain.replace(/_/g, " ")}
      color={color}
      size="small"
      sx={{ fontWeight: 600, fontSize: "0.7rem" }}
    />
  );
}
