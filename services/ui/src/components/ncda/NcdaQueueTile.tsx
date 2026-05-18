/**
 * NCDA active-learning queue tile (Stage 9c).
 *
 * Surfaces low-confidence linkage decisions, all cohort 3 cases, and pairs
 * with seen_missing or treatment_missing flags. Reviewer feedback feeds
 * the nightly retraining job (Stage 11).
 */
"use client";

import * as React from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";

import { NCDA_COHORT_LABELS, NCDA_QUEUE_REASON_LABELS } from "@/lib/ncdaLabels";
import { NcdaCohort } from "@/lib/ncdaPathway";

export type QueueReason = keyof typeof NCDA_QUEUE_REASON_LABELS;

export interface NcdaQueueItem {
  patient_id: string;
  pathway_id: string;
  cohort: NcdaCohort;
  reason: QueueReason;
  ftr_date?: string | null;
  dx_date?: string | null;
  linkage_probability?: number | null;
  site_key?: string | null;
}

export interface NcdaQueueTileProps {
  items: NcdaQueueItem[];
  onOpen?: (item: NcdaQueueItem) => void;
}

export function NcdaQueueTile({ items, onOpen }: NcdaQueueTileProps) {
  return (
    <Box data-testid="ncda-queue-tile" sx={{ p: 2 }}>
      <Stack direction="row" alignItems="center" spacing={2} mb={2}>
        <Typography variant="h6">Cases to review</Typography>
        <Chip label={`${items.length} in queue`} size="small" />
      </Stack>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Patient</TableCell>
            <TableCell>Cohort</TableCell>
            <TableCell>Why it is here</TableCell>
            <TableCell>Urgent referral</TableCell>
            <TableCell>Cancer found</TableCell>
            <TableCell>Confidence</TableCell>
            <TableCell>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => (
            <TableRow key={`${item.patient_id}:${item.pathway_id}`}>
              <TableCell>{item.patient_id}</TableCell>
              <TableCell>{NCDA_COHORT_LABELS[item.cohort]}</TableCell>
              <TableCell>{NCDA_QUEUE_REASON_LABELS[item.reason]}</TableCell>
              <TableCell>{item.ftr_date ?? "Not found"}</TableCell>
              <TableCell>{item.dx_date ?? "Not found"}</TableCell>
              <TableCell>
                {item.linkage_probability !== null && item.linkage_probability !== undefined
                  ? `${(item.linkage_probability * 100).toFixed(0)}%`
                  : "-"}
              </TableCell>
              <TableCell>
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => onOpen?.(item)}
                  data-testid="ncda-queue-open"
                >
                  Open
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

export default NcdaQueueTile;
