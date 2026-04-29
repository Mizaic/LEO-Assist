/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-D5B9FE5F
 *   DI: DI-6E1B71A4
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-D5B9FE5F")
 */
"use client";

/**
 * Symptoms at Referral section.
 *
 * Plain-English heatmaps: for each suspected cancer type, every cell shows
 * "X of Y patients with this symptom were later told they had cancer".
 * PPV = patients_with_cancer / patients_with_feature.
 *
 * Symptom evidence uses SNOMED codes from the ncda-symptoms ValueSet
 * (concept + IS_A descendants), queried from DOCUMENTS relationships on
 * encounters within +/-7 days of the referral date.
 *
 * Copy targets a reading age of 9-11 (per `.cursor/rules/health-literacy.mdc`).
 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";

import SectionCard from "./SectionCard";
import SymptomsDrilldownDialog from "./SymptomsDrilldownDialog";
import type {
  AuditSymptomPpvRow,
  AuditPpvByCancerTypeRow,
  AuditSymptoms,
} from "@/lib/analyticsApi";
import { fetchAuditSymptoms } from "@/lib/analyticsApi";

interface Props {
  loading?: boolean;
  error?: string | null;
  orgId?: string;
  dateFrom?: string;
  dateTo?: string;
}

// ---------------------------------------------------------------------------
// Colour helpers
// ---------------------------------------------------------------------------

function ppvColor(ppv: number): string {
  if (ppv >= 75) return "#15803d";
  if (ppv >= 50) return "#0369a1";
  if (ppv >= 25) return "#92400e";
  return "#9ca3af";
}

function ppvBackground(ppv: number, weak: boolean): string {
  if (weak) return "rgba(156,163,175,0.09)";
  if (ppv <= 0) return "rgba(156,163,175,0.09)";
  if (ppv < 25) return "rgba(156,163,175,0.14)";
  if (ppv < 50) return "rgba(146,64,14,0.14)";
  if (ppv < 75) return "rgba(3,105,161,0.16)";
  return "rgba(21,128,61,0.18)";
}

function ppvStrength(ppv: number, n: number): "strong" | "moderate" | "weak" | "none" {
  if (n < 2) return "weak";
  if (ppv <= 0) return "none";
  if (ppv >= 50) return "strong";
  if (ppv >= 25) return "moderate";
  return "weak";
}

// ---------------------------------------------------------------------------
// Group + sort helpers
// ---------------------------------------------------------------------------

interface SiteGroup {
  cancer_type: string;
  rows: AuditSymptomPpvRow[];
  strongCount: number;
  moderateCount: number;
}

function buildGroups(
  rows: AuditSymptomPpvRow[],
  minN: number,
  showZero: boolean,
): SiteGroup[] {
  const map = new Map<string, AuditSymptomPpvRow[]>();
  for (const row of rows) {
    if (!map.has(row.cancer_type)) map.set(row.cancer_type, []);
    map.get(row.cancer_type)!.push(row);
  }

  return Array.from(map.entries())
    .map(([cancer_type, siteRows]) => {
      const filtered = siteRows
        .filter((r) => r.patients_with_feature >= minN)
        .filter((r) => showZero || r.ppv_pct > 0)
        .sort((a, b) => {
          const sa = ppvStrength(a.ppv_pct, a.patients_with_feature);
          const sb = ppvStrength(b.ppv_pct, b.patients_with_feature);
          const order = { strong: 0, moderate: 1, weak: 2, none: 3 };
          if (order[sb] !== order[sa]) return order[sa] - order[sb];
          if (b.patients_with_feature !== a.patients_with_feature)
            return b.patients_with_feature - a.patients_with_feature;
          if (b.ppv_pct !== a.ppv_pct) return b.ppv_pct - a.ppv_pct;
          return a.symptom.localeCompare(b.symptom);
        });
      const strongCount = filtered.filter(
        (r) => ppvStrength(r.ppv_pct, r.patients_with_feature) === "strong",
      ).length;
      const moderateCount = filtered.filter(
        (r) => ppvStrength(r.ppv_pct, r.patients_with_feature) === "moderate",
      ).length;
      return { cancer_type, rows: filtered, strongCount, moderateCount };
    })
    .filter((g) => g.rows.length > 0)
    .sort((a, b) => {
      if (b.strongCount !== a.strongCount) return b.strongCount - a.strongCount;
      if (b.moderateCount !== a.moderateCount) return b.moderateCount - a.moderateCount;
      return b.rows.length - a.rows.length;
    });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PpvHeroCard({ row }: { row: AuditPpvByCancerTypeRow }) {
  const ppvLabel = row.ppv_pct == null ? "n/a" : `${row.ppv_pct}%`;
  return (
    <Tooltip
      arrow
      title={
        <Box sx={{ fontSize: "0.78rem" }}>
          <strong>{row.cancer_type}</strong>
          <br />
          {row.referrals_n} {row.referrals_n === 1 ? "person was" : "people were"} sent to hospital because the GP thought it might be {row.cancer_type.toLowerCase()} cancer.
          <br />
          {row.diagnosed_in_year_n} of them later found out they did have cancer.
          <br />
          That works out as {ppvLabel}.
        </Box>
      }
    >
      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          p: 1.5,
          display: "flex",
          flexDirection: "column",
          gap: 0.5,
          minWidth: 130,
        }}
      >
        <Typography
          variant="caption"
          sx={{ fontWeight: 700, lineHeight: 1.2, color: "text.secondary" }}
        >
          {row.cancer_type}
        </Typography>
        <Stack direction="row" alignItems="baseline" spacing={0.5}>
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              color: row.ppv_pct != null ? ppvColor(row.ppv_pct) : "text.disabled",
            }}
          >
            {ppvLabel}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            had cancer
          </Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          {row.diagnosed_in_year_n} of {row.referrals_n} {row.referrals_n === 1 ? "referral" : "referrals"}
        </Typography>
        {row.provisional && (
          <Chip
            size="small"
            label="Not final yet"
            aria-label="Provisional"
            color="warning"
            variant="outlined"
            sx={{ fontSize: "0.65rem", height: 18, alignSelf: "flex-start" }}
          />
        )}
      </Box>
    </Tooltip>
  );
}

interface SymptomCellProps {
  row: AuditSymptomPpvRow;
  maxN: number;
}

function SymptomCell({ row, maxN }: SymptomCellProps) {
  const strength = ppvStrength(row.ppv_pct, row.patients_with_feature);
  const weak = strength === "weak" || strength === "none";
  const barPct = Math.round((row.patients_with_feature / Math.max(maxN, 1)) * 100);

  const strengthBadge: Record<string, { label: string; color: string } | null> = {
    strong: { label: "Strong", color: "#15803d" },
    moderate: { label: "Moderate", color: "#0369a1" },
    weak: null,
    none: null,
  };

  const featureLabel = row.patients_with_feature === 1 ? "person had" : "people had";
  const cancerVerb = row.patients_with_cancer === 1 ? "was" : "were";

  return (
    <Tooltip
      arrow
      title={
        <Box sx={{ fontSize: "0.78rem" }}>
          <strong>{row.symptom}</strong>
          <br />
          {row.patients_with_feature} {featureLabel} this around the time of referral.
          <br />
          {row.patients_with_cancer} of them {cancerVerb} later told they had {row.cancer_type.toLowerCase()} cancer.
          <br />
          That works out as {row.ppv_pct}%.
          {row.patients_with_feature < 2 && (
            <>
              <br />
              <em>Only 1 patient -- the number is too small to trust on its own.</em>
            </>
          )}
        </Box>
      }
    >
      <Box
        sx={{
          border: "1px solid",
          borderColor: weak ? "divider" : ppvColor(row.ppv_pct),
          borderRadius: 1,
          backgroundColor: ppvBackground(row.ppv_pct, weak),
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          opacity: weak ? 0.65 : 1,
          transition: "opacity 0.15s",
          "&:hover": { opacity: 1 },
        }}
      >
        {/* PPV colour bar at top: width = denominator fraction */}
        <Box
          sx={{
            height: 3,
            width: `${barPct}%`,
            backgroundColor: ppvColor(row.ppv_pct),
            opacity: weak ? 0.4 : 0.7,
          }}
        />
        <Box sx={{ p: 0.85, display: "flex", flexDirection: "column", gap: 0.6 }}>
          <Typography
            variant="caption"
            sx={{
              color: weak ? "text.secondary" : "text.primary",
              fontWeight: weak ? 400 : 600,
              lineHeight: 1.25,
              fontSize: "0.72rem",
            }}
          >
            {row.symptom}
          </Typography>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography
              variant="body2"
              sx={{
                color: ppvColor(row.ppv_pct),
                fontWeight: 800,
                fontSize: "0.85rem",
              }}
            >
              {row.ppv_pct}%
            </Typography>
            <Stack direction="row" alignItems="center" gap={0.5}>
              {strengthBadge[strength] && (
                <Box
                  sx={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    backgroundColor: strengthBadge[strength]!.color,
                    flexShrink: 0,
                  }}
                />
              )}
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ fontSize: "0.68rem" }}
              >
                {row.patients_with_cancer} of {row.patients_with_feature} had cancer
              </Typography>
            </Stack>
          </Stack>
        </Box>
      </Box>
    </Tooltip>
  );
}

interface SiteCardProps {
  group: SiteGroup;
  hiddenCount: number;
}

function TumourSiteHeatmapCard({ group, hiddenCount }: SiteCardProps) {
  const maxN = Math.max(1, ...group.rows.map((r) => r.patients_with_feature));

  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 1.5,
        backgroundColor: "background.paper",
        display: "flex",
        flexDirection: "column",
        gap: 1,
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {group.cancer_type}
        </Typography>
        <Stack direction="row" gap={0.5} alignItems="center">
          {group.strongCount > 0 && (
            <Chip
              size="small"
              label={`${group.strongCount} strong signal${group.strongCount !== 1 ? "s" : ""}`}
              sx={{
                fontSize: "0.6rem",
                height: 16,
                backgroundColor: "rgba(21,128,61,0.14)",
                color: "#15803d",
              }}
            />
          )}
          {group.moderateCount > 0 && (
            <Chip
              size="small"
              label={`${group.moderateCount} medium signal${group.moderateCount !== 1 ? "s" : ""}`}
              sx={{
                fontSize: "0.6rem",
                height: 16,
                backgroundColor: "rgba(3,105,161,0.14)",
                color: "#0369a1",
              }}
            />
          )}
        </Stack>
      </Stack>
      <Box
        role="list"
        aria-label={`Symptoms found around the time of referral for ${group.cancer_type}`}
        sx={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(190px, 1fr))",
          gap: 0.75,
        }}
      >
        {group.rows.map((row) => (
          <SymptomCell
            key={`${row.cancer_type}-${row.symptom}`}
            row={row}
            maxN={maxN}
          />
        ))}
      </Box>
      {hiddenCount > 0 && (
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ pt: 0.5, borderTop: "1px solid", borderColor: "divider" }}
        >
          {hiddenCount} symptom{hiddenCount !== 1 ? "s" : ""} hidden by current filter
        </Typography>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main section
// ---------------------------------------------------------------------------

const MIN_N_OPTIONS = [1, 2, 3, 5] as const;
type MinN = (typeof MIN_N_OPTIONS)[number];

export default function SymptomsSection({
  loading: parentLoading,
  error: parentError,
  orgId,
  dateFrom,
  dateTo,
}: Props) {
  const [data, setData] = useState<AuditSymptoms | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [drilldownOpen, setDrilldownOpen] = useState(false);
  const [minN, setMinN] = useState<MinN>(2);
  const [showZero, setShowZero] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAuditSymptoms(orgId, dateFrom, dateTo)
      .then((d) => { if (!cancelled) setData(d); })
      .catch(() => { if (!cancelled) setError("Unable to load symptom data."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [orgId, dateFrom, dateTo]);

  const groups = useMemo(
    () => buildGroups(data?.rows ?? [], minN, showZero),
    [data, minN, showZero],
  );

  // Hidden counts per site (for "N hidden" footer)
  const hiddenCounts = useMemo(() => {
    const map = new Map<string, number>();
    if (!data?.rows) return map;
    const shown = new Set(
      groups.flatMap((g) => g.rows.map((r) => `${r.cancer_type}||${r.symptom}`)),
    );
    for (const row of data.rows) {
      const k = `${row.cancer_type}||${row.symptom}`;
      if (!shown.has(k)) map.set(row.cancer_type, (map.get(row.cancer_type) ?? 0) + 1);
    }
    return map;
  }, [data, groups]);

  const totalShown = groups.reduce((n, g) => n + g.rows.length, 0);

  return (
    <SectionCard
      id="section-symptoms"
      title="Symptoms at Referral"
      description="How often each symptom led to a real cancer. We look at the symptoms patients had in the week before or after their referral. For each symptom, we count how many of those patients turned out to have cancer."
      availability="ready"
      loading={parentLoading || loading}
      error={parentError || error}
    >
      {!loading && data ? (
        <Box>
          {/* Referral-cohort PPV hero cards */}
          {data.ppv_by_suspected_cancer_type.length > 0 && (
            <Box sx={{ mb: 2.5 }}>
              <Typography
                variant="subtitle2"
                sx={{ fontWeight: 600, fontSize: "0.85rem", mb: 0.25 }}
              >
                How many referrals turned out to be cancer
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 1, fontSize: "0.72rem" }}
              >
                Each card is one type of cancer the GP suspected. The big number
                shows how many of those referrals were later confirmed as cancer.
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {data.ppv_by_suspected_cancer_type.map((row) => (
                  <PpvHeroCard key={row.cancer_type} row={row} />
                ))}
              </Stack>
            </Box>
          )}

          {/* Filter controls + section header */}
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            flexWrap="wrap"
            gap={1}
            sx={{ mb: 1.5 }}
          >
            <Box>
              <Typography
                variant="subtitle2"
                sx={{ fontWeight: 600, fontSize: "0.85rem" }}
              >
                Which symptoms led to cancer, by tumour site
                {totalShown > 0 && (
                  <Typography
                    component="span"
                    variant="caption"
                    color="text.secondary"
                    sx={{ ml: 1 }}
                  >
                    ({totalShown} symptom and cancer pairings &middot; {data.cohort_n}{" "}
                    patients)
                  </Typography>
                )}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.25, display: "block", fontSize: "0.7rem" }}
              >
                Strongest signals first. The thin bar at the top of each box shows
                how many patients had that symptom -- a longer bar means more
                patients.
              </Typography>
            </Box>

            <Stack direction="row" alignItems="center" gap={1}>
              {/* Min denominator filter */}
              <Stack direction="row" alignItems="center" gap={0.5}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ whiteSpace: "nowrap" }}
                >
                  Min patients
                </Typography>
                <ToggleButtonGroup
                  size="small"
                  exclusive
                  value={minN}
                  onChange={(_, v) => v != null && setMinN(v as MinN)}
                  sx={{ "& .MuiToggleButton-root": { px: 1, py: 0.25, fontSize: "0.72rem" } }}
                >
                  {MIN_N_OPTIONS.map((n) => (
                    <ToggleButton key={n} value={n}>
                      {n}+
                    </ToggleButton>
                  ))}
                </ToggleButtonGroup>
              </Stack>

              {/* Show/hide zero PPV */}
              <Chip
                size="small"
                label={showZero ? "Hide 0% PPV" : "Show 0% PPV"}
                variant={showZero ? "filled" : "outlined"}
                onClick={() => setShowZero((v) => !v)}
                sx={{ fontSize: "0.7rem", cursor: "pointer" }}
              />

              <Button
                variant="outlined"
                size="small"
                onClick={() => setDrilldownOpen(true)}
              >
                Breakdown
              </Button>
            </Stack>
          </Stack>

          {/* Colour legend */}
          <Stack
            direction="row"
            gap={1.5}
            sx={{ mb: 1.5, flexWrap: "wrap" }}
            alignItems="center"
          >
            {[
              { label: "75%+ had cancer", color: "#15803d" },
              { label: "50-74% had cancer", color: "#0369a1" },
              { label: "25-49% had cancer", color: "#92400e" },
              { label: "Under 25% had cancer", color: "#9ca3af" },
            ].map(({ label, color }) => (
              <Stack key={label} direction="row" alignItems="center" gap={0.5}>
                <Box
                  sx={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    backgroundColor: color,
                    flexShrink: 0,
                  }}
                />
                <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.68rem" }}>
                  {label}
                </Typography>
              </Stack>
            ))}
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ fontSize: "0.68rem", opacity: 0.75 }}
            >
              Faded boxes mean fewer than {minN} patients had the symptom -- the number is too small to trust.
            </Typography>
          </Stack>

          {/* Heatmap cards grid */}
          {groups.length > 0 ? (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(290px, 1fr))",
                gap: 1.25,
              }}
            >
              {groups.map((group) => (
                <TumourSiteHeatmapCard
                  key={group.cancer_type}
                  group={group}
                  hiddenCount={hiddenCounts.get(group.cancer_type) ?? 0}
                />
              ))}
            </Box>
          ) : (
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ py: 1.5, fontSize: "0.82rem" }}
            >
              No symptoms match your filters. Try a smaller &quot;Min patients&quot;
              number, or turn on &quot;Show 0% PPV&quot; to include symptoms where
              nobody was found to have cancer.
            </Typography>
          )}

          <Typography
            variant="caption"
            color="text.secondary"
            display="block"
            sx={{ mt: 2 }}
          >
            How to read each box: out of all patients with this symptom around
            the time of referral, how many were later told they had cancer. The
            same patient can show up in more than one box if they had more than
            one symptom. Symptoms come from the patient&apos;s record in the week
            before or after the referral. PPV (positive predictive value) is the
            clinical name for the percentage shown.
          </Typography>

          <SymptomsDrilldownDialog
            open={drilldownOpen}
            onClose={() => setDrilldownOpen(false)}
            orgId={orgId}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />
        </Box>
      ) : !loading ? (
        <Typography variant="body2" color="text.secondary" sx={{ py: 1.5 }}>
          Symptom data is not yet available for this practice.
        </Typography>
      ) : (
        <Box sx={{ display: "flex", justifyContent: "center", py: 3 }}>
          <CircularProgress size={28} />
        </Box>
      )}
    </SectionCard>
  );
}
