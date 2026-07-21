/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Skeleton from "@mui/material/Skeleton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Sankey, Tooltip as RechartsTooltip, ResponsiveContainer } from "recharts";

import { fetchAuditNSSOutcomes, type AuditNSSOutcomes } from "@/lib/analyticsApi";
import { useOrgId } from "@/context/OrgContext";
import { useAnalyticsDateFilter } from "@/context/AnalyticsDateFilterContext";
import { SankeyNode } from "@/components/editor/elements/chartSankeyFunnel";

const NSS_SOURCE_LABEL = "NSS Referral";

function buildSankeyData(data: AuditNSSOutcomes) {
  const nodes: { name: string }[] = [{ name: NSS_SOURCE_LABEL }];
  const links: { source: number; target: number; value: number }[] = [];

  data.outcomes.forEach((item, idx) => {
    nodes.push({ name: item.outcome });
    links.push({ source: 0, target: idx + 1, value: item.n });
  });

  return { nodes, links };
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function NSSOutcomeSankeyDialog({ open, onClose }: Props) {
  const orgId = useOrgId();
  const { dateFrom, dateTo } = useAnalyticsDateFilter();

  const [data, setData] = useState<AuditNSSOutcomes | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setData(null);
    setError(null);

    fetchAuditNSSOutcomes(orgId ?? undefined, dateFrom ?? undefined, dateTo ?? undefined)
      .then((result) => {
        if (cancelled) return;
        setData(result);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Failed to load NSS outcome data.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, orgId, dateFrom, dateTo]);

  const sankeyData = data ? buildSankeyData(data) : null;
  const hasCancerPct =
    data && data.total_nss > 0
      ? Math.round((data.cancer_diagnosed_n / data.total_nss) * 100)
      : null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      aria-labelledby="nss-sankey-dialog-title"
    >
      <DialogTitle id="nss-sankey-dialog-title" sx={{ pr: 6 }}>
        <Typography component="span" sx={{ fontWeight: 700, fontSize: "1rem" }}>
          NSS Referral Outcomes
        </Typography>
        <IconButton
          aria-label="Close NSS outcomes dialog"
          onClick={onClose}
          size="small"
          sx={{ position: "absolute", right: 12, top: 12 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <Divider />

      <DialogContent sx={{ pt: 2 }}>
        {loading && (
          <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
            <Skeleton variant="text" width="60%" />
            <Skeleton variant="rectangular" height={240} />
          </Box>
        )}

        {error && (
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        )}

        {!loading && !error && data && (
          <>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" color="text.secondary">
                <strong>{data.total_nss}</strong> NSS (non-site-specific) referral
                {data.total_nss !== 1 ? "s" : ""} in selected period
                {hasCancerPct !== null && (
                  <>
                    {" "}&mdash; <strong>{data.cancer_diagnosed_n}</strong> (
                    {hasCancerPct}%) resulted in a coded cancer diagnosis
                  </>
                )}
                .
              </Typography>
            </Box>

            {data.total_nss === 0 ? (
              <Typography
                variant="body2"
                color="text.secondary"
                sx={{ textAlign: "center", py: 4, fontStyle: "italic" }}
              >
                No NSS referral episodes found in the selected date range.
              </Typography>
            ) : sankeyData && sankeyData.nodes.length > 1 ? (
              <Box
                sx={{ width: "100%", height: 300 }}
                role="img"
                aria-label={`Sankey diagram showing outcomes for ${data.total_nss} NSS referrals. ${data.cancer_diagnosed_n} patients received a cancer diagnosis.`}
              >
                <ResponsiveContainer width="100%" height="100%">
                  <Sankey
                    data={sankeyData as { nodes: { name: string }[]; links: { source: number; target: number; value: number }[] }}
                    nodePadding={20}
                    nodeWidth={10}
                    linkCurvature={0.5}
                    node={<SankeyNode />}
                    margin={{ top: 10, right: 160, bottom: 10, left: 10 }}
                  >
                    <RechartsTooltip
                      formatter={(value, _name, item) => {
                        const payload = (
                          item as {
                            payload?: {
                              source?: { name?: string };
                              target?: { name?: string };
                            };
                          }
                        )?.payload;
                        const source = payload?.source?.name ?? "";
                        const target = payload?.target?.name ?? "";
                        const numeric =
                          typeof value === "number" ? value : Number(value ?? 0);
                        return [
                          `${numeric} patient${numeric !== 1 ? "s" : ""}`,
                          `${source} -> ${target}`,
                        ];
                      }}
                    />
                  </Sankey>
                </ResponsiveContainer>
              </Box>
            ) : null}

            {data.outcomes.length > 0 && (
              <Box
                component="table"
                sx={{
                  mt: 2,
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: "0.8rem",
                }}
                aria-label="NSS referral outcome breakdown"
              >
                <Box component="thead">
                  <Box component="tr" sx={{ borderBottom: "2px solid", borderColor: "divider" }}>
                    <Box component="th" sx={{ textAlign: "left", py: 0.5, fontWeight: 600 }}>Outcome</Box>
                    <Box component="th" sx={{ textAlign: "right", py: 0.5, fontWeight: 600, width: 60 }}>n</Box>
                    <Box component="th" sx={{ textAlign: "right", py: 0.5, fontWeight: 600, width: 60 }}>%</Box>
                  </Box>
                </Box>
                <Box component="tbody">
                  {data.outcomes.map((row) => {
                    const pct = data.total_nss > 0
                      ? Math.round((row.n / data.total_nss) * 100)
                      : 0;
                    return (
                      <Box
                        key={row.outcome}
                        component="tr"
                        sx={{ borderBottom: "1px solid", borderColor: "divider" }}
                      >
                        <Box component="td" sx={{ py: 0.5 }}>{row.outcome}</Box>
                        <Box component="td" sx={{ py: 0.5, textAlign: "right" }}>{row.n}</Box>
                        <Box component="td" sx={{ py: 0.5, textAlign: "right" }}>{pct}%</Box>
                      </Box>
                    );
                  })}
                </Box>
              </Box>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
