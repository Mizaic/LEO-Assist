/**
 * Atlas trace:
 *   DI: DI-CC0BD732 (per-episode SBAR with coherence)
 *   DI: DI-885930F8 (canonical episode-level code)
 *   DI: DI-E8FE404D (cross-encounter coding QA)
 *   UN: UN-782EE657 (clinician sees one SBAR per episode)
 *
 * Rendered inside the PatientDetailDrawer when the user selects a single
 * EpisodeOfCare. Replaces the prior patient-level SBAR card. Three
 * structural goals:
 *
 *   1. Show the canonical episode code with intent + confidence so the
 *      reviewer can see what the system thinks the episode IS at a glance.
 *   2. Surface deterministic coherence flags AND cross-encounter coding
 *      QA flags as accordioned alerts, each with the specific review
 *      action a reviewer can take.
 *   3. Render the per-episode SBAR via CDN LeoSbarHost when
 *      assessmentId is present (DI-A898556B).
 */
"use client";

import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { LeoSbarHost } from "@/components/sbar-final/LeoSbarHost";

export type CoherenceFlagCode =
  | "narrative_contradiction"
  | "code_narrative_drift";

export type CodingQAFlagCode =
  | "trajectory_inversion"
  | "code_contradiction"
  | "site_mismatch";

export type FlagSeverity = "low" | "medium" | "high";

export interface CoherenceFlag {
  code: CoherenceFlagCode;
  severity: FlagSeverity;
  summary: string;
  citation?: string;
}

export interface CodingQAFlag {
  flagId: string;
  code: CodingQAFlagCode;
  severity: FlagSeverity;
  summary: string;
  encounterIds: string[];
  citation?: string;
}

export interface CanonicalCode {
  conceptId: string;
  displayName: string;
  intent: "confirmed" | "suspected";
  confidence: number;
}

export interface EpisodeDetail {
  episodeId: string;
  patientId: string;
  suspectedSite: string;
  status: "open" | "closed" | "benign_closure";
  encounterIds: string[];
  canonicalCode?: CanonicalCode | null;
  sbarMarkdown?: string | null;
  /** Canonical Assessment id for CDN leo-sbar mount. */
  assessmentId?: string | null;
  coherenceFlags?: CoherenceFlag[];
  codingQaFlags?: CodingQAFlag[];
}

export interface EpisodeDetailPanelProps {
  episode: EpisodeDetail;
  onAcceptCode?: () => void;
  onOverrideCode?: () => void;
  onResolveCoherenceFlag?: (code: CoherenceFlagCode) => void;
  onResolveCodingQaFlag?: (flagId: string) => void;
  onRegenerateSbar?: () => void;
}

const SEVERITY_COLOR: Record<FlagSeverity, "info" | "warning" | "error"> = {
  low: "info",
  medium: "warning",
  high: "error",
};

const COHERENCE_REVIEW_LABEL: Record<CoherenceFlagCode, string> = {
  narrative_contradiction: "Reconcile assessment vs recommendation",
  code_narrative_drift: "Confirm canonical code matches narrative",
};

const CODING_QA_REVIEW_LABEL: Record<CodingQAFlagCode, string> = {
  trajectory_inversion: "Re-review encounter sequence",
  code_contradiction: "Resolve mutually exclusive codes",
  site_mismatch: "Move encounter to correct episode",
};

export default function EpisodeDetailPanel({
  episode,
  onAcceptCode,
  onOverrideCode,
  onResolveCoherenceFlag,
  onResolveCodingQaFlag,
  onRegenerateSbar,
}: EpisodeDetailPanelProps) {
  const coherenceFlags = episode.coherenceFlags ?? [];
  const codingQaFlags = episode.codingQaFlags ?? [];

  return (
    <Box
      data-testid="episode-detail-panel"
      sx={{ display: "flex", flexDirection: "column", gap: 2 }}
    >
      <EpisodeHeader episode={episode} />

      <CanonicalCodeCard
        canonical={episode.canonicalCode ?? null}
        onAccept={onAcceptCode}
        onOverride={onOverrideCode}
      />

      {coherenceFlags.length > 0 && (
        <Box data-testid="episode-detail-coherence-flags">
          {coherenceFlags.map((flag) => (
            <Alert
              key={flag.code}
              severity={SEVERITY_COLOR[flag.severity]}
              data-testid={`coherence-flag-${flag.code}`}
              sx={{ mb: 1 }}
              action={
                onResolveCoherenceFlag && (
                  <Button
                    size="small"
                    color="inherit"
                    onClick={() => onResolveCoherenceFlag(flag.code)}
                    data-testid={`coherence-flag-${flag.code}-resolve`}
                  >
                    {COHERENCE_REVIEW_LABEL[flag.code]}
                  </Button>
                )
              }
            >
              <AlertTitle>SBAR coherence: {flag.code}</AlertTitle>
              {flag.summary}
            </Alert>
          ))}
        </Box>
      )}

      {codingQaFlags.length > 0 && (
        <Box data-testid="episode-detail-coding-qa-flags">
          {codingQaFlags.map((flag) => (
            <Alert
              key={flag.flagId}
              severity={SEVERITY_COLOR[flag.severity]}
              data-testid={`coding-qa-flag-${flag.flagId}`}
              sx={{ mb: 1 }}
              action={
                onResolveCodingQaFlag && (
                  <Button
                    size="small"
                    color="inherit"
                    onClick={() => onResolveCodingQaFlag(flag.flagId)}
                    data-testid={`coding-qa-flag-${flag.flagId}-resolve`}
                  >
                    {CODING_QA_REVIEW_LABEL[flag.code]}
                  </Button>
                )
              }
            >
              <AlertTitle>Coding QA: {flag.code}</AlertTitle>
              {flag.summary}
              {flag.encounterIds.length > 0 && (
                <Box sx={{ mt: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    Encounters: {flag.encounterIds.join(", ")}
                  </Typography>
                </Box>
              )}
            </Alert>
          ))}
        </Box>
      )}

      <SbarSection
        assessmentId={episode.assessmentId ?? null}
        markdown={episode.sbarMarkdown ?? ""}
        episodeId={episode.episodeId}
        onRegenerate={onRegenerateSbar}
      />
    </Box>
  );
}

function EpisodeHeader({ episode }: { episode: EpisodeDetail }) {
  return (
    <Box data-testid="episode-detail-header">
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="h6" component="h2">
          Episode {episode.episodeId}
        </Typography>
        <Chip
          size="small"
          label={`Site: ${episode.suspectedSite}`}
          data-testid="episode-detail-site-chip"
        />
        <Chip
          size="small"
          label={`Status: ${episode.status}`}
          color={episode.status === "benign_closure" ? "success" : "default"}
          data-testid="episode-detail-status-chip"
        />
        <Chip
          size="small"
          label={`${episode.encounterIds.length} encounters`}
          variant="outlined"
          data-testid="episode-detail-encounter-count"
        />
      </Stack>
    </Box>
  );
}

function CanonicalCodeCard({
  canonical,
  onAccept,
  onOverride,
}: {
  canonical: CanonicalCode | null;
  onAccept?: () => void;
  onOverride?: () => void;
}) {
  if (!canonical) {
    return (
      <Alert
        severity="info"
        data-testid="canonical-code-empty"
      >
        No canonical episode code derived yet. Run the episode-aware coder
        to derive one from the encounter codes.
      </Alert>
    );
  }
  const intentColor = canonical.intent === "confirmed" ? "primary" : "warning";
  return (
    <Box
      data-testid="canonical-code-card"
      sx={{
        p: 2,
        borderRadius: 1.5,
        border: "1px solid",
        borderColor: "divider",
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Canonical episode code
        </Typography>
        <Chip
          size="small"
          color={intentColor}
          label={canonical.intent}
          data-testid="canonical-code-intent"
        />
        <Chip
          size="small"
          variant="outlined"
          label={`confidence ${(canonical.confidence * 100).toFixed(0)}%`}
          data-testid="canonical-code-confidence"
        />
      </Stack>
      <Typography
        variant="body2"
        sx={{ mt: 1 }}
        data-testid="canonical-code-display"
      >
        {canonical.displayName} ({canonical.conceptId})
      </Typography>
      {(onAccept || onOverride) && (
        <Stack direction="row" spacing={1} sx={{ mt: 1.5 }}>
          {onAccept && (
            <Button
              size="small"
              variant="contained"
              onClick={onAccept}
              data-testid="canonical-code-accept"
            >
              Accept canonical code
            </Button>
          )}
          {onOverride && (
            <Button
              size="small"
              variant="outlined"
              onClick={onOverride}
              data-testid="canonical-code-override"
            >
              Override
            </Button>
          )}
        </Stack>
      )}
    </Box>
  );
}

function SbarSection({
  assessmentId,
  markdown,
  episodeId,
  onRegenerate,
}: {
  assessmentId: string | null;
  markdown: string;
  episodeId: string;
  onRegenerate?: () => void;
}) {
  if (!assessmentId && !markdown) {
    return (
      <Alert
        severity="info"
        data-testid="episode-sbar-empty"
        action={
          onRegenerate && (
            <Button
              size="small"
              color="inherit"
              onClick={onRegenerate}
              data-testid="episode-sbar-generate"
            >
              Generate SBAR
            </Button>
          )
        }
      >
        No SBAR for this episode yet.
      </Alert>
    );
  }
  return (
    <Box data-testid="episode-sbar-section">
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          Episode SBAR
        </Typography>
        <Chip
          size="small"
          color="info"
          label={`Scope: episode ${episodeId}`}
          data-testid="episode-sbar-scope-chip"
        />
        {onRegenerate && (
          <Button
            size="small"
            onClick={onRegenerate}
            data-testid="episode-sbar-regenerate"
          >
            Regenerate
          </Button>
        )}
      </Stack>
      {assessmentId ? (
        <LeoSbarHost
          assessmentId={assessmentId}
          testId={`episode-${episodeId}-sbar`}
        />
      ) : (
        <Alert severity="warning" data-testid="episode-sbar-missing-id">
          This episode SBAR is missing an assessment id. Open Validation Lab
          or regenerate the SBAR so the CDN widget can load it.
        </Alert>
      )}
    </Box>
  );
}
