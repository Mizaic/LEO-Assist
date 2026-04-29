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
 * Shows clinical PPV heatmaps: for each suspected cancer type, each symptom
 * cell shows the count of patients with the symptom at the referral encounter
 * (+/-7 days) and the count who received a confirmed cancer diagnosis.
 * PPV = patients_with_cancer / patients_with_feature.
 *
 * Symptom evidence uses SNOMED codes from the ncda-symptoms ValueSet
 * (concept + IS_A descendants), queried from DOCUMENTS relationships on
 * encounters within +/-7 days of the referral date.
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
          PPV
        </Typography>
      </Stack>
      <Typography variant="caption" color="text.secondary">
        {row.referrals_n} referrals &middot; {row.diagnosed_in_year_n} diagnosed
      </Typography>
      {row.provisional && (
        <Chip
          size="small"
          label="Provisional"
          color="warning"
          variant="outlined"
          sx={{ fontSize: "0.65rem", height: 18, alignSelf: "flex-start" }}
        />
      )}
    </Box>
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

  return (
    <Tooltip
      arrow
      title={
        <Box sx={{ fontSize: "0.78rem" }}>
          <strong>{row.symptom}</strong>
          <br />
          {row.patients_with_cancer} of {row.patients_with_feature} patients diagnosed
          <br />
          PPV {row.ppv_pct}%
          {row.patients_with_feature < 2 && (
            <>
              <br />
              <em>Low confidence: only 1 patient</em>
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
                {row.patients_with_cancer}/{row.patients_with_feature}
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
              label={`${group.strongCount} strong`}
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
              label={`${group.moderateCount} moderate`}
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
        aria-label={`${group.cancer_type} symptom PPV heatmap`}
        sx={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(155px, 1fr))",
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
      description="Clinical PPV per symptom and cancer type. Counts distinct patients whose referral encounter (+/-7 days) was coded with each symptom from the NCDA symptoms ValueSet; PPV is patients with feature who received a confirmed cancer diagnosis."
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
                sx={{ fontWeight: 600, fontSize: "0.85rem", mb: 1 }}
              >
                Referral-cohort PPV by suspected cancer type
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
                Symptom PPV heatmaps by suspected cancer type
                {totalShown > 0 && (
                  <Typography
                    component="span"
                    variant="caption"
                    color="text.secondary"
                    sx={{ ml: 1 }}
                  >
                    ({totalShown} symptom combinations &middot; {data.cohort_n}{" "}
                    patients)
                  </Typography>
                )}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ mt: 0.25, display: "block", fontSize: "0.7rem" }}
              >
                Sorted by signal strength. Cell width of top bar = patients with
                feature as % of max.
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
              { label: "PPV >= 75%", color: "#15803d" },
              { label: "50-74%", color: "#0369a1" },
              { label: "25-49%", color: "#92400e" },
              { label: "< 25%", color: "#9ca3af" },
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
              Dimmed cells = low confidence (n &lt; {minN})
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
              No symptoms match the current filter. Try lowering the minimum
              patient count or enabling &quot;Show 0% PPV&quot;.
            </Typography>
          )}

          <Typography
            variant="caption"
            color="text.secondary"
            display="block"
            sx={{ mt: 2 }}
          >
            PPV = patients with symptom who received a confirmed cancer diagnosis
            / all patients with that symptom (for the suspected cancer type at
            referral). Symptoms sourced from NCDA symptoms ValueSet SNOMED codes
            on encounters within +/-7 days of referral date.
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
