"use client";

/**
 * Prior Consultations -- year-on-year evolution section.
 *
 * Implements NCDA Section 7 of the primary-care pro forma:  the
 * number of consultations for cancer-related symptoms in the year
 * before the FTR.  Backed by the Claude Haiku 4.5 enrichment pass
 * (libs/oncology/prior_consultations.py) which scans every clinical
 * encounter in the year-prior window, drops administrative noise,
 * classifies each survivor as cancer-related or not, and proposes
 * NCDA "multiple consultations" factor codes with evidence quotes.
 *
 * Renders four cards (2018 NCDA baseline + previous two calendar
 * years + current calendar year).  Each live year card carries an
 * "Open detail" zoom button that opens a dialog with:
 *   - Distribution histogram (0 / 1 / 2-3 / 4-6 / 7+ consultations)
 *   - Top NCDA factor codes proposed by the LLM
 *   - Mean per-episode contact-type breakdown (f2f, phone, nurse,
 *     email, specialist clinic, home visit, phlebotomy, result
 *     review).
 *   - LLM cost telemetry (Haiku token spend per cohort).
 */

import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Typography from "@mui/material/Typography";

import {
  fetchAuditPriorConsultations,
  type AuditPriorConsultations,
  type AuditSectionResult,
} from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { resolveBenchmarkValue } from "./BenchmarkLegend";

import SectionCard from "./SectionCard";
import EvolutionDetailDialog from "./EvolutionDetailDialog";
import EvolutionYearCard, { EvolutionLegendSwatch } from "./EvolutionYearCard";
import { useAuditYearWindows, BASELINE_YEAR } from "./_useAuditYearWindows";

const ACCENT = "#7C3AED";       // purple to distinguish from safety-net blue + obstruction red
const C_BENCH18 = "#92400E";    // shared baseline brown

const BUCKET_ORDER = ["0", "1", "2-3", "4-6", "7+"] as const;
type BucketKey = (typeof BUCKET_ORDER)[number];

const BUCKET_COLOURS: Record<BucketKey, string> = {
  "0":   "#9CA3AF",
  "1":   "#A7F3D0",
  "2-3": "#7C3AED",   // accent — first NCDA-positive bucket
  "4-6": "#5B21B6",
  "7+":  "#3B0764",
};

const BUCKET_LABELS: Record<BucketKey, string> = {
  "0":   "0 consultations",
  "1":   "1 consultation",
  "2-3": "2-3 consultations (NCDA \"multiple\")",
  "4-6": "4-6 consultations",
  "7+":  "7+ consultations",
};

/** Human-readable labels for each NCDA "multiple consultations"
 *  factor code -- mirror libs/oncology/prior_consultations.py
 *  NCDA_FACTOR_LABELS so the dialog matches the GP pro forma wording
 *  exactly. */
const FACTOR_LABELS: Record<string, string> = {
  co_morbidity_blurring:
    "Co-morbidity blurring picture",
  different_initial_diagnosis:
    "Symptoms suggested different initial diagnosis",
  different_malignancy:
    "Symptoms suggested different malignancy",
  incomplete_symptom_account:
    "Didn't have a full account of symptoms",
  low_perceived_malignancy_probability:
    "Perceived low probability of malignancy",
  frequent_attender_vague_symptoms:
    "Frequent attender with vague symptoms",
  declined_investigation:
    "Declined investigation or examination",
  declined_referral:
    "Declined referral or admission",
  did_not_attend_followup:
    "Did not attend for follow-up",
  abnormal_result_not_followed_up:
    "Abnormal result not followed up",
  poor_communication_with_patient:
    "Poor communication with the patient",
  inadequate_history_taken:
    "Inadequate history taken",
  examination_not_performed:
    "Appropriate examination not performed",
  investigation_not_ordered:
    "Appropriate investigation not ordered",
  wrong_specialty_referral:
    "Referred to the 'wrong' specialty",
  poor_communication_within_practice:
    "Poor communication within the practice",
  seen_by_multiple_health_professionals:
    "Seen by multiple health professionals",
  reassurance_from_negative_investigation:
    "Reassurance from negative investigation",
  investigation_suggested_benign_cause:
    "Investigation suggested benign cause",
  consultations_to_discuss_test_results:
    "Consultation(s) to discuss test results",
  no_reason: "No reason",
  other_reason: "Other",
  no_multiple_consultations: "No multiple consultations",
  not_known: "Not known",
};

/** Contact-type meta -- ordering and labels for the dialog table. */
const CONTACT_META: Array<{ key: keyof NonNullable<AuditPriorConsultations["mean_per_episode"]>; label: string }> = [
  { key: "f2f",                label: "Face-to-face (clinic)" },
  { key: "phone",              label: "Telephone" },
  { key: "nurse",              label: "Nurse / Nurse Practitioner" },
  { key: "email",              label: "Email / secure message" },
  { key: "specialist_clinic",  label: "Specialist clinic attendance" },
  { key: "home_visit",         label: "Home visit" },
  { key: "phlebotomy",         label: "Phlebotomy / blood draw" },
  { key: "result_review",      label: "Result review (auto-filed)" },
];

interface Props {
  result: AuditSectionResult<AuditPriorConsultations> | null;
  loading: boolean;
  error?: string | null;
  orgSelected?: boolean;
}

function formatPct(v: number | null | undefined): string | null {
  if (v == null) return null;
  return `${Math.round(v * 10) / 10}%`;
}

interface BucketRowProps {
  label: string;
  count: number;
  pct: number;
  total: number;
  colour: string;
  emphasis?: boolean;
}

function BucketRow({ label, count, pct, total, colour, emphasis }: BucketRowProps) {
  const widthPct = total > 0 ? (count / total) * 100 : 0;
  return (
    <Box sx={{ mb: 1.25 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 1,
          mb: 0.5,
        }}
      >
        <Typography
          variant="body2"
          sx={{
            fontSize: "0.82rem",
            fontWeight: emphasis ? 700 : 500,
            color: "text.primary",
          }}
        >
          {label}
        </Typography>
        <Typography
          variant="body2"
          sx={{
            fontSize: "0.85rem",
            fontWeight: 700,
            color: colour,
            whiteSpace: "nowrap",
          }}
        >
          {count}{" "}
          <Box component="span" sx={{ color: "text.secondary", fontWeight: 500 }}>
            ({pct.toFixed(1)}%)
          </Box>
        </Typography>
      </Box>
      <Box
        role="progressbar"
        aria-valuenow={Math.round(widthPct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${count} of ${total}`}
        sx={{
          height: 8,
          borderRadius: 1,
          bgcolor: "grey.100",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            width: `${widthPct}%`,
            height: "100%",
            bgcolor: colour,
            transition: "width 200ms ease-out",
          }}
        />
      </Box>
    </Box>
  );
}

function PriorConsultationsBreakdownChart({
  data,
  year,
}: {
  data: AuditPriorConsultations;
  year: number;
}) {
  const total = data.total_episodes ?? 0;
  const buckets = data.buckets ?? { "0": 0, "1": 0, "2-3": 0, "4-6": 0, "7+": 0 };
  const bucketsPct = data.buckets_pct ?? {
    "0": 0, "1": 0, "2-3": 0, "4-6": 0, "7+": 0,
  };
  const multiPct = data.multiple_consultations_pct ?? 0;
  const multiN = data.multiple_consultations_n ?? 0;
  const meanTotal = data.mean_per_episode?.total ?? 0;
  const meanByType = data.mean_per_episode;
  const topFactors = (data.top_factors ?? []).slice(0, 8);
  const enrichedN = data.enriched_n ?? 0;

  if (total === 0) {
    return (
      <Alert severity="info" sx={{ fontSize: "0.85rem" }}>
        No confirmed-cancer episodes closed in {year} yet, so there is
        nothing to break down. Once a case in this window reaches a
        diagnosis or benign-closure outcome, the LLM enrichment pass
        will populate this view.
      </Alert>
    );
  }

  return (
    <Box>
      {/* Headline tiles ------------------------------------------- */}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
          gap: 2,
          mb: 2.5,
        }}
      >
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            px: 2,
            py: 1.5,
          }}
        >
          <Typography
            variant="caption"
            sx={{
              color: "text.secondary",
              textTransform: "uppercase",
              letterSpacing: 0.5,
              fontWeight: 600,
              fontSize: "0.7rem",
              display: "block",
            }}
          >
            Multiple consultations (&ge;2)
          </Typography>
          <Typography
            sx={{
              fontSize: "1.4rem",
              fontWeight: 700,
              color: ACCENT,
              lineHeight: 1.1,
              mt: 0.25,
            }}
          >
            {multiPct.toFixed(1)}%
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
            {multiN} of {total} confirmed cancers
          </Typography>
        </Box>
        <Box
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            px: 2,
            py: 1.5,
          }}
        >
          <Typography
            variant="caption"
            sx={{
              color: "text.secondary",
              textTransform: "uppercase",
              letterSpacing: 0.5,
              fontWeight: 600,
              fontSize: "0.7rem",
              display: "block",
            }}
          >
            Mean cancer-related consultations
          </Typography>
          <Typography
            sx={{
              fontSize: "1.4rem",
              fontWeight: 700,
              color: ACCENT,
              lineHeight: 1.1,
              mt: 0.25,
            }}
          >
            {meanTotal.toFixed(2)}
          </Typography>
          <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.78rem" }}>
            per episode (over {enrichedN} enriched)
          </Typography>
        </Box>
      </Box>

      {/* Distribution histogram ----------------------------------- */}
      <Typography
        variant="subtitle2"
        sx={{
          fontSize: "0.78rem",
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: 0.5,
          color: "text.secondary",
          mb: 1,
        }}
      >
        Distribution -- consultations per episode
      </Typography>
      {BUCKET_ORDER.map((b) => {
        const isMulti = b !== "0" && b !== "1";
        return (
          <BucketRow
            key={b}
            label={BUCKET_LABELS[b]}
            count={buckets[b] ?? 0}
            pct={bucketsPct[b] ?? 0}
            total={total}
            colour={BUCKET_COLOURS[b]}
            emphasis={isMulti}
          />
        );
      })}

      {/* Top NCDA factors ----------------------------------------- */}
      {topFactors.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography
            variant="subtitle2"
            sx={{
              fontSize: "0.78rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              color: "text.secondary",
              mb: 1,
            }}
          >
            Top NCDA factors -- why multiple consultations?
          </Typography>
          {topFactors.map((f) => {
            const label = FACTOR_LABELS[f.factor] ?? f.factor;
            const pct = total > 0 ? (f.n / total) * 100 : 0;
            return (
              <BucketRow
                key={f.factor}
                label={label}
                count={f.n}
                pct={pct}
                total={total}
                colour={ACCENT}
              />
            );
          })}
          <Typography
            variant="caption"
            sx={{
              display: "block",
              mt: 1,
              fontSize: "0.74rem",
              color: "text.secondary",
              fontStyle: "italic",
            }}
          >
            Factors are proposed by Claude Haiku 4.5 with episode-level
            evidence quotes; clinician reviewers confirm or reject in
            the final NCDA pro forma.  Human-judgment-only factors
            (e.g. inadequate history taken, poor communication) are
            never auto-proposed -- they appear in the pro forma as
            manual checkboxes for the GP.
          </Typography>
        </Box>
      )}

      {/* Contact-type means --------------------------------------- */}
      {meanByType && (
        <Box sx={{ mt: 3 }}>
          <Typography
            variant="subtitle2"
            sx={{
              fontSize: "0.78rem",
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              color: "text.secondary",
              mb: 1,
            }}
          >
            Mean per-episode consultations by contact type
          </Typography>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr 1fr", md: "1fr 1fr 1fr 1fr" },
              gap: 1.5,
            }}
          >
            {CONTACT_META.map((c) => (
              <Box
                key={c.key}
                sx={{
                  px: 1.25,
                  py: 1,
                  border: "1px solid",
                  borderColor: "divider",
                  borderRadius: 1,
                }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    display: "block",
                    fontSize: "0.7rem",
                    color: "text.secondary",
                    fontWeight: 600,
                  }}
                >
                  {c.label}
                </Typography>
                <Typography
                  sx={{ fontSize: "1.05rem", fontWeight: 700, color: "text.primary" }}
                >
                  {(meanByType[c.key] ?? 0).toFixed(2)}
                </Typography>
              </Box>
            ))}
          </Box>
        </Box>
      )}

      {/* Telemetry footer ----------------------------------------- */}
      <Box
        sx={{
          mt: 3,
          p: 1.5,
          borderRadius: 1.5,
          bgcolor: "grey.50",
          border: "1px solid",
          borderColor: "divider",
        }}
      >
        <Typography
          variant="caption"
          sx={{
            display: "block",
            fontSize: "0.72rem",
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            color: "text.secondary",
            mb: 0.5,
          }}
        >
          LLM enrichment
        </Typography>
        <Typography
          variant="caption"
          sx={{ display: "block", fontSize: "0.78rem", color: "text.primary" }}
        >
          Claude Haiku 4.5 classified <strong>{enrichedN}</strong> of{" "}
          {total} confirmed-cancer episodes for cancer-relatedness and
          NCDA factor inference.
          {(data.unrelated_filtered_total ?? 0) > 0 && (
            <>
              {" "}
              <strong>{data.unrelated_filtered_total}</strong> encounter
              {(data.unrelated_filtered_total ?? 0) === 1 ? " was" : "s were"}{" "}
              filtered out as clearly unrelated to the cancer pathway
              (LTC review, vaccine clinic, midwife, etc.) and so are
              NOT in the headline.
            </>
          )}{" "}
          Cohort spend: <strong>${(data.llm_cost_usd ?? 0).toFixed(4)}</strong>{" "}
          ({(data.llm_input_tokens ?? 0).toLocaleString()} in /{" "}
          {(data.llm_output_tokens ?? 0).toLocaleString()} out tokens
          across {data.llm_calls ?? 0} call
          {(data.llm_calls ?? 0) === 1 ? "" : "s"}).
        </Typography>
      </Box>

      <Typography
        variant="caption"
        sx={{
          display: "block",
          mt: 2,
          fontSize: "0.74rem",
          color: "text.secondary",
          fontStyle: "italic",
        }}
      >
        Detection window: 365 days before the FTR (matching the NCDA
        Section 7 wording).  Encounters tagged f2f / telephone / nurse
        / email / specialist clinic / home visit / phlebotomy count
        toward the consultation tally; auto-filed result rows do NOT
        count (they're surfaced separately as result reviews).
        Administrative noise (SMS sends, booking confirmations,
        repeat scripts, vaccine invitations) is dropped before the
        LLM call to keep token spend low.
      </Typography>
    </Box>
  );
}

export default function PriorConsultationsSection({
  result,
  loading,
  error,
  orgSelected = false,
}: Props) {
  const orgId = useOrgId();
  const bm = result?.benchmark?.metrics;

  const { liveYears } = useAuditYearWindows<AuditPriorConsultations>(
    fetchAuditPriorConsultations,
    { orgId },
  );

  // 2018 NCDA published the % of cancer pathways with multiple
  // consultations.  When the benchmark set provides a value (key
  // ``prior_consultations.multiple_consultations_pct``) we use it;
  // otherwise the baseline card shows an em-dash with a tooltip
  // explaining the gap, rather than a fabricated comparator.
  const baselinePct = useMemo(() => {
    return resolveBenchmarkValue(
      bm,
      "prior_consultations.multiple_consultations_pct",
      orgSelected,
    );
  }, [bm, orgSelected]);

  const [detailYear, setDetailYear] = useState<number | null>(null);
  const detailState = liveYears.find((y) => y.year === detailYear) ?? null;

  return (
    <SectionCard
      id="section-prior-consultations"
      title="Prior Consultations (NCDA Section 7)"
      description={
        "The number of patient consultations for cancer-related symptoms in the year before the fast-track referral.  " +
        "The 2018 NCDA baseline is GP-confirmed -- GPs reviewed their own cases and counted the relevant consultations.  " +
        "Live year figures are auto-classified by Claude Haiku 4.5: every clinical encounter in the year-prior window is " +
        "tagged related / unrelated, contact-type identified, and NCDA 'multiple consultations' factor codes proposed " +
        "with evidence quotes.  Each card covers a Jan-Dec calendar year, counted by year of diagnosis or benign closure.  " +
        "Open the detail panel on a live year to see the distribution, top factors, and contact-type breakdown."
      }
      availability="pipeline_pending"
      loading={loading}
      loadingSkeletonVariant="segmentedCards"
      error={error}
    >
      <Box sx={{ display: "flex", gap: 2, mb: 1.5, flexWrap: "wrap" }}>
        <EvolutionLegendSwatch colour={C_BENCH18} label="2018 NCDA baseline" dashed />
        <EvolutionLegendSwatch colour={ACCENT} label="Live year (Haiku-classified)" />
      </Box>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <EvolutionYearCard
            yearLabel={String(BASELINE_YEAR)}
            headlineValue={formatPct(baselinePct)}
            headlineSubLabel="GP-confirmed"
            isBaseline
            baselineFootnote={
              baselinePct == null
                ? "No published 2019 NCDA value loaded for this scope yet -- once the benchmark file ships a value for prior_consultations.multiple_consultations_pct it will appear here."
                : "2019 NCDA: GPs retrospectively reviewed their own cases and counted the relevant consultations in the year before the FTR. This is a clinician-confirmed figure, not an algorithmic estimate."
            }
          />
        </Grid>
        {liveYears.map((state) => {
          const hasBreakdown =
            state.data != null && state.data.buckets != null;
          return (
            <Grid key={state.year} size={{ xs: 12, sm: 6, md: 3 }}>
              <EvolutionYearCard
                yearLabel={String(state.year)}
                loading={state.loading}
                error={state.error}
                totalN={state.data?.total_episodes ?? 0}
                headlineValue={formatPct(state.data?.multiple_consultations_pct)}
                headlineSubLabel="multiple consultations"
                accentColor={ACCENT}
                onZoom={
                  hasBreakdown ? () => setDetailYear(state.year) : undefined
                }
                zoomAriaLabel={`Open ${state.year} prior-consultations breakdown`}
              />
            </Grid>
          );
        })}
      </Grid>

      <EvolutionDetailDialog
        open={detailState != null}
        onClose={() => setDetailYear(null)}
        title={
          detailState
            ? `Prior consultations -- ${detailState.year} breakdown`
            : "Prior consultations -- breakdown"
        }
        subtitle={
          "NCDA Section 7: cancer-related consultations in the year before the FTR. " +
          "Encounters auto-classified by Claude Haiku 4.5; NCDA factor codes proposed with evidence quotes. " +
          "Distribution buckets show the spread of cancer-related consultation counts; top factors show " +
          "the LLM's proposed reasons; contact-type means show the average per episode by encounter category."
        }
        maxWidth="md"
      >
        {detailState?.data ? (
          <PriorConsultationsBreakdownChart
            data={detailState.data}
            year={detailState.year}
          />
        ) : (
          <Alert severity="info" sx={{ fontSize: "0.85rem" }}>
            Loading breakdown...
          </Alert>
        )}
      </EvolutionDetailDialog>
    </SectionCard>
  );
}
