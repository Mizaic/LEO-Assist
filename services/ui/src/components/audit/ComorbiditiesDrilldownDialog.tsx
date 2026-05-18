/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4DADBA3F")
 */
"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Tab from "@mui/material/Tab";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";

import {
  fetchAuditComorbiditiesDrilldown,
  type AuditComorbidityBreakdownSlice,
  type AuditComorbiditiesDrilldown,
} from "@/lib/analyticsApi";

interface Props {
  open: boolean;
  onClose: () => void;
  orgId?: string;
  dateFrom?: string;
  dateTo?: string;
}

function SliceTables({
  title,
  slices,
}: {
  title: string;
  slices: AuditComorbidityBreakdownSlice[];
}) {
  if (slices.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
        No rows for {title}.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      {slices.map((slice) => (
        <Box key={slice.slice_key}>
          <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
            {slice.slice_label}{" "}
            <Typography component="span" variant="caption" color="text.secondary">
              (n = {slice.cohort_n})
            </Typography>
          </Typography>
          <Table size="small" sx={{ "& td": { py: 0.5, fontSize: "0.78rem" } }}>
            <TableHead>
              <TableRow>
                <TableCell>Condition</TableCell>
                <TableCell align="right">n</TableCell>
                <TableCell align="right">%</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {slice.rows
                .filter((r) => r.n > 0)
                .map((row) => (
                  <TableRow key={`${slice.slice_key}-${row.condition}`}>
                    <TableCell>{row.condition}</TableCell>
                    <TableCell align="right">{row.n}</TableCell>
                    <TableCell align="right">{row.pct}%</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </Box>
      ))}
    </Box>
  );
}

export default function ComorbiditiesDrilldownDialog({
  open,
  onClose,
  orgId,
  dateFrom,
  dateTo,
}: Props) {
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AuditComorbiditiesDrilldown | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchAuditComorbiditiesDrilldown(orgId, dateFrom, dateTo)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setError("Unable to load comorbidity breakdown.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, orgId, dateFrom, dateTo]);

  const panel =
    data == null ? null : tab === 0 ? (
      <SliceTables title="age" slices={data.by_age_band} />
    ) : tab === 1 ? (
      <SliceTables title="gender" slices={data.by_gender} />
    ) : (
      <SliceTables title="referral outcome" slices={data.by_referral_outcome} />
    );

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth scroll="paper">
      <DialogTitle>Comorbidity breakdown</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Prevalence within each slice of the audited cohort. Cancer-diagnosis
          slices use SNOMED concepts from the cancer_types ValueSet (expanded to
          descendants) on the episode with the latest referral date in the
          selected window. &quot;Referral without cancer diagnosis&quot; means a
          referral milestone without a confirmed cancer diagnosis on that
          episode.
        </Typography>
        {loading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress size={32} />
          </Box>
        )}
        {error && (
          <Typography color="error" variant="body2">
            {error}
          </Typography>
        )}
        {!loading && data && (
          <>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
              Total patients in cohort: {data.total_patients}
            </Typography>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              sx={{ mb: 2 }}
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab label="By age band" />
              <Tab label="By gender" />
              <Tab label="By referral outcome" />
            </Tabs>
            {panel}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
