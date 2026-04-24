/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-146D93D0
 *   Also implements: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-146D93D0")
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import ExpandMore from "@mui/icons-material/ExpandMore";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { fetchEncounterConcepts } from "@/lib/missionControlApi";
import type { MissionEpisode } from "@/lib/missionControlApi";

interface ConceptRow {
  encounter_id: string;
  encounter_date: string;
  concept_id: string;
  concept_name: string;
  semantic_tag: string;
  assertion: string;
  confidence: number | null;
  source: string | null;
  value: number | null;
  unit: string | null;
  reference_range: string | null;
}

function AssertionChip({ assertion }: { assertion: string }) {
  const colours: Record<string, "success" | "warning" | "error" | "default"> = {
    present: "success",
    historical: "default",
    possible: "warning",
    absent: "error",
    negated: "error",
  };
  return (
    <Chip
      label={assertion}
      size="small"
      color={colours[assertion] ?? "default"}
      variant="outlined"
      sx={{ fontSize: "0.65rem" }}
    />
  );
}

function ObsValueCell({
  value,
  unit,
  referenceRange,
  semanticTag,
}: {
  value: number | null;
  unit: string | null;
  referenceRange: string | null;
  semanticTag: string;
}) {
  const isObs =
    semanticTag.toLowerCase().replace(/\s/g, "") === "observableentity";
  if (!isObs) return <TableCell />;
  if (value == null && !unit) return <TableCell sx={{ color: "text.disabled", fontSize: "0.7rem" }}>--</TableCell>;
  const label = [
    value != null ? String(value) : "",
    unit ?? "",
  ]
    .filter(Boolean)
    .join(" ");
  const tooltip = referenceRange ? `Ref: ${referenceRange}` : undefined;
  return (
    <Tooltip title={tooltip ?? ""} arrow disableHoverListener={!tooltip}>
      <TableCell sx={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
        {label}
      </TableCell>
    </Tooltip>
  );
}

function ConfidenceCell({ confidence }: { confidence: number | null }) {
  if (confidence == null) return <TableCell>--</TableCell>;
  const pct = Math.round(confidence * 100);
  const colour = pct >= 80 ? "success.main" : pct >= 60 ? "warning.main" : "error.main";
  return (
    <Tooltip title={`Model confidence: ${pct}%`} arrow>
      <TableCell sx={{ color: colour, fontWeight: pct < 60 ? 700 : 400 }}>
        {pct}%
      </TableCell>
    </Tooltip>
  );
}

interface Props {
  patientId: string;
  episode: MissionEpisode;
  /** Bumped by the parent drawer after an inline coding edit so this
   *  tab refetches its patient-scoped concept list and shows the
   *  saved state without forcing a drawer close/reopen. */
  refreshKey?: number;
}

export default function CodedDataTab({ patientId, episode, refreshKey = 0 }: Props) {
  const [rows, setRows] = useState<ConceptRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scope, setScope] = useState<"linked" | "all">("linked");

  useEffect(() => {
    setLoading(true);
    fetchEncounterConcepts(patientId)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load coded data."))
      .finally(() => setLoading(false));
  }, [patientId, refreshKey]);

  const linkedIdsFromEdges = episode.linked_encounter_ids ?? [];
  const linkedIdsFromMilestones = (episode.milestones ?? []).map((m) => m.encounter_id);
  const linkedEncounterIds = new Set(
    [...linkedIdsFromEdges, ...linkedIdsFromMilestones].map((id) => String(id))
  );
  const linkedRows = rows.filter((r) => linkedEncounterIds.has(r.encounter_id));
  const nonLinkedRows = rows.filter((r) => !linkedEncounterIds.has(r.encounter_id));
  const visibleRows = scope === "linked" ? linkedRows : rows;
  const keyedVisibleRows = useMemo(() => {
    const keyCounts = new Map<string, number>();
    return visibleRows.map((row) => {
      const baseKey = [
        row.encounter_id,
        row.encounter_date,
        row.concept_id,
        row.assertion,
        row.semantic_tag,
        row.source ?? "",
      ].join("|");
      const seenCount = keyCounts.get(baseKey) ?? 0;
      keyCounts.set(baseKey, seenCount + 1);
      return { row, key: `${baseKey}|${seenCount}` };
    });
  }, [visibleRows]);
  const hasExplicitLinks = linkedEncounterIds.size > 0;

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress aria-label="Loading coded data" />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!rows.length) {
    return (
      <Alert severity="info">
        No coded concepts found for this patient. The pipeline may not have run yet.
      </Alert>
    );
  }

  return (
    <Box>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: "block" }}>
        {hasExplicitLinks
          ? "Showing coded concepts linked to this episode by default. Use All coded concepts if you need wider patient context."
          : "No direct encounter-to-episode links were found for this episode yet. Showing all coded concepts can help you review context while linkage is rebuilt."}
      </Typography>
      <Box sx={{ display: "flex", gap: 1, mb: 1, flexWrap: "wrap" }}>
        <Chip
          label={`Episode linked (${linkedRows.length})`}
          size="small"
          color={scope === "linked" ? "primary" : "default"}
          variant={scope === "linked" ? "filled" : "outlined"}
          onClick={() => setScope("linked")}
        />
        <Chip
          label={`All coded concepts (${rows.length})`}
          size="small"
          color={scope === "all" ? "primary" : "default"}
          variant={scope === "all" ? "filled" : "outlined"}
          onClick={() => setScope("all")}
        />
      </Box>
      <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Date</TableCell>
              <TableCell>Concept</TableCell>
              <TableCell>SNOMED code</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Value / unit</TableCell>
              <TableCell>Assertion</TableCell>
              <TableCell>Confidence</TableCell>
              <TableCell>Source</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {keyedVisibleRows.map(({ row, key }) => (
              <TableRow key={key} hover>
                <TableCell sx={{ whiteSpace: "nowrap" }}>
                  {row.encounter_date?.slice(0, 10) ?? "--"}
                </TableCell>
                <TableCell>{row.concept_name}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: "0.7rem" }}>
                  {row.concept_id}
                </TableCell>
                <TableCell sx={{ fontSize: "0.7rem" }}>{row.semantic_tag}</TableCell>
                <ObsValueCell
                  value={row.value}
                  unit={row.unit}
                  referenceRange={row.reference_range}
                  semanticTag={row.semantic_tag}
                />
                <TableCell>
                  <AssertionChip assertion={row.assertion} />
                </TableCell>
                <ConfidenceCell confidence={row.confidence} />
                <TableCell sx={{ fontSize: "0.7rem" }}>{row.source ?? "model"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
      </Table>
      {scope === "linked" && !hasExplicitLinks && (
        <Alert severity="warning" sx={{ mt: 2 }}>
          We could not find any encounters explicitly linked to this episode.
          This usually means pathway linkage has not been fully written to the graph yet.
        </Alert>
      )}
      {scope === "linked" && nonLinkedRows.length > 0 && (
        <Accordion sx={{ mt: 2 }} elevation={0}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="body2" color="text.secondary">
              Other coded concepts not linked to this episode ({nonLinkedRows.length})
            </Typography>
          </AccordionSummary>
          <AccordionDetails sx={{ pt: 0 }}>
            <Typography variant="caption" color="text.secondary">
              Expand only when you need full patient context.
            </Typography>
          </AccordionDetails>
        </Accordion>
      )}
    </Box>
  );
}
