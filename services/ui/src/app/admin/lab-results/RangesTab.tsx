/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import Alert from "@mui/material/Alert";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { color } from "@leo/design-system/tokens";

import ConfirmDialog from "@/components/ConfirmDialog";

import { ConfirmRows } from "./labConfigForm";
import { RangeFormCard, type RangeOrgOption } from "./RangeFormCard";
import { ownerCopy, rangeConfirmRows } from "./rangeDraft";
import type { LabReferenceRange } from "./types";
import { useRangesTab } from "./useRangesTab";

interface Props {
  conceptId: string;
  ranges: LabReferenceRange[];
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}

function fmtRange(low: number | null | undefined, high: number | null | undefined): string {
  if (low == null && high == null) return "-";
  return (low ?? "-") + " to " + (high ?? "-");
}

export default function RangesTab({ conceptId, ranges, onRefresh, onToast }: Props) {
  const page = useRangesTab({ conceptId, onRefresh, onToast });
  return (
    <Stack spacing={2}>
      {page.error ? (
        <Alert severity="error" onClose={() => page.setError(null)}>
          {page.error}
        </Alert>
      ) : null}
      <RangeTable rows={ranges} orgs={page.orgs} onDelete={page.setDeleteId} />
      <RangeFormCard
        draft={page.draft}
        orgs={page.orgs}
        onPatch={page.patchDraft}
        onSubmit={() => page.setPending(true)}
        saving={page.saving}
      />
      {page.pending ? (
        <ConfirmDialog
          title="Add this reference range?"
          body={confirmBody(page.draft.orgId)}
          confirmLabel="Add range"
          busy={page.saving}
          maxWidth="sm"
          onConfirm={() => void page.handleAdd()}
          onCancel={() => page.setPending(false)}
        >
          <ConfirmRows
            rows={rangeConfirmRows(page.draft, orgName(page.orgs, page.draft.orgId))}
          />
        </ConfirmDialog>
      ) : null}
      {page.deleteId ? (
        <ConfirmDialog
          title="Remove reference range?"
          body="Remove this reference range? This cannot be undone."
          confirmLabel="Remove"
          variant="danger"
          onConfirm={() => page.handleDelete(page.deleteId as string)}
          onCancel={() => page.setDeleteId(null)}
        />
      ) : null}
    </Stack>
  );
}

function confirmBody(orgId: string): string {
  if (!orgId.trim()) {
    return "Check the range, then save. Cancel leaves the list unchanged.";
  }
  return (
    "This overlay applies only to the chosen organisation. " +
    "Other organisations keep their own ranges."
  );
}

function orgName(orgs: RangeOrgOption[], orgId: string): string | undefined {
  return orgs.find((org) => org.id === orgId)?.name;
}

function RangeTable({
  rows,
  orgs,
  onDelete,
}: {
  rows: LabReferenceRange[];
  orgs: RangeOrgOption[];
  onDelete: (id: string) => void;
}) {
  if (rows.length === 0) {
    return (
      <Typography variant="body2" sx={{ color: color.text.secondary }}>
        No ranges yet. Add the first range below.
      </Typography>
    );
  }
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Owner</TableCell>
          <TableCell>Sex</TableCell>
          <TableCell>Age (years)</TableCell>
          <TableCell>Normal</TableCell>
          <TableCell>Critical</TableCell>
          <TableCell width={48} />
        </TableRow>
      </TableHead>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.range_id}>
            <TableCell>{ownerCopy(r.org_id || "", orgName(orgs, r.org_id || ""))}</TableCell>
            <TableCell>{r.sex || "all"}</TableCell>
            <TableCell>
              {r.age_min ?? "-"} - {r.age_max ?? "-"}
            </TableCell>
            <TableCell>{fmtRange(r.low, r.high)}</TableCell>
            <TableCell>
              {r.critical_low ?? "-"} / {r.critical_high ?? "-"}
            </TableCell>
            <TableCell align="right">
              <IconButton
                size="small"
                aria-label={"Remove range for " + (r.sex || "all")}
                onClick={() => onDelete(r.range_id)}
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
