/**
 * QuickTestResults -- per-stage entity breakdown for a completed quick-run.
 *
 * Stage snapshot terms are plain strings (entity surface forms captured after
 * each pipeline subgraph). The final entity list has richer objects with
 * label, assertion, and confidence fields.
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import MedicalServicesOutlinedIcon from "@mui/icons-material/MedicalServicesOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";

import type { CodedEntity, ExtractedEntity, QuickRunResult } from "./types";

const STAGE_ORDER = [
  "extraction",
  "post_processing",
  "relation_linking",
  "extraction_check",
];

const STAGE_LABELS: Record<string, string> = {
  extraction: "1. Extraction (LLM raw output)",
  post_processing: "2. Post-processing",
  relation_linking: "3. Relation linking",
  extraction_check: "4. Extraction check",
};

const TAG_COLOURS: Record<
  string,
  "default" | "primary" | "secondary" | "error" | "warning" | "info" | "success"
> = {
  disorder: "error",
  finding: "primary",
  procedure: "secondary",
  "observable entity": "info",
  situation: "warning",
  substance: "success",
  product: "success",
};

function tagColour(tag: string) {
  return TAG_COLOURS[tag?.toLowerCase()] ?? "default";
}

function StageTermList({ terms }: { terms: string[] }) {
  if (!terms?.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ pl: 1, py: 0.5 }}>
        No entities at this stage.
      </Typography>
    );
  }
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        p: 1,
        display: "flex",
        flexWrap: "wrap",
        gap: 0.5,
        maxHeight: 160,
        overflowY: "auto",
      }}
    >
      {terms.map((term, i) => (
        <Chip
          key={i}
          label={term}
          size="small"
          variant="outlined"
          sx={{ fontSize: "0.72rem", fontFamily: "monospace" }}
        />
      ))}
    </Box>
  );
}

function FinalEntityTable({ entities }: { entities: ExtractedEntity[] }) {
  if (!entities?.length) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ pl: 1, py: 0.5 }}>
        No final entities returned.
      </Typography>
    );
  }
  return (
    <Box
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        overflowY: "auto",
        maxHeight: 320,
      }}
    >
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600, width: "45%" }}>Text</TableCell>
            <TableCell sx={{ fontWeight: 600, width: "25%" }}>Tag</TableCell>
            <TableCell sx={{ fontWeight: 600, width: "20%" }}>Assertion</TableCell>
            <TableCell sx={{ fontWeight: 600, width: "10%" }}>Conf.</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {entities.map((t, i) => (
            <TableRow key={i} hover>
              <TableCell sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                {t.text}
              </TableCell>
              <TableCell>
                <Chip
                  label={t.label ?? t.semantic_tag ?? "unknown"}
                  color={tagColour(t.label ?? t.semantic_tag ?? "")}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: "0.68rem" }}
                />
              </TableCell>
              <TableCell sx={{ fontSize: "0.75rem" }}>
                {t.assertion ?? "present"}
              </TableCell>
              <TableCell sx={{ fontSize: "0.75rem" }}>
                {t.confidence != null ? (t.confidence * 100).toFixed(0) + "%" : "-"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

function StageSummary({
  stageKey,
  terms,
  entityCount,
  prevCount,
}: {
  stageKey: string;
  terms: string[];
  entityCount: number;
  prevCount: number | null;
}) {
  const delta = prevCount != null ? entityCount - prevCount : null;
  return (
    <Box sx={{ mb: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          {STAGE_LABELS[stageKey] ?? stageKey}
        </Typography>
        <Chip label={`${entityCount} entities`} size="small" />
        {delta != null && delta !== 0 && (
          <Chip
            label={delta > 0 ? `+${delta} added` : `${delta} removed`}
            color={delta > 0 ? "success" : "warning"}
            size="small"
            variant="outlined"
          />
        )}
      </Stack>
      <StageTermList terms={terms} />
    </Box>
  );
}

interface Props {
  result: QuickRunResult;
}

export default function QuickTestResults({ result }: Props) {
  const snapshots = result.stage_snapshots ?? {};
  const presentKeys = STAGE_ORDER.filter((k) => k in snapshots);
  const extraKeys = Object.keys(snapshots).filter(
    (k) => !STAGE_ORDER.includes(k),
  );
  const allKeys = [...presentKeys, ...extraKeys];
  const isError = result.worker_status === "error";
  const isEmpty = result.worker_status === "empty_extraction";

  return (
    <Box sx={{ mt: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
        {isError ? (
          <Chip
            icon={<WarningAmberOutlinedIcon />}
            label="Pipeline error"
            color="error"
            size="small"
          />
        ) : isEmpty ? (
          <Chip
            icon={<WarningAmberOutlinedIcon />}
            label="Empty extraction"
            color="warning"
            size="small"
          />
        ) : (
          <Chip
            icon={<CheckCircleOutlineIcon />}
            label={`${result.entity_count ?? 0} final entities`}
            color="success"
            size="small"
          />
        )}
        {result.model_provider && (
          <Typography variant="body2" color="text.secondary">
            {result.model_provider}
            {result.model_tier ? ` / ${result.model_tier}` : ""}
          </Typography>
        )}
      </Stack>

      {!allKeys.length && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          No stage snapshots captured. Check that the pipeline plan supports
          capture_validation_output.
        </Typography>
      )}

      {allKeys.map((key, idx) => {
        const snap = snapshots[key];
        const prevCount =
          idx > 0 ? (snapshots[allKeys[idx - 1]]?.entity_count ?? null) : null;
        return (
          <StageSummary
            key={key}
            stageKey={key}
            terms={snap.terms ?? []}
            entityCount={snap.entity_count ?? 0}
            prevCount={prevCount}
          />
        );
      })}

      {(result.entities?.length ?? 0) > 0 && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
            Final entities (after all post-processing)
          </Typography>
          <FinalEntityTable entities={result.entities ?? []} />
        </Box>
      )}

      {(result.coded_entities?.length ?? 0) > 0 && (
        <>
          <Divider sx={{ my: 3 }} />
          <CodingResultsTable codes={result.coded_entities ?? []} />
        </>
      )}

      {result.status === "completed" &&
        (result.coded_entities?.length ?? 0) === 0 &&
        (result.worker_status === "completed" || result.worker_status === "needs_review") && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            No SNOMED codes written yet. The persist step may still be running,
            or no entities passed the coding threshold.
          </Typography>
        )}
    </Box>
  );
}

const ASSERTION_COLOUR: Record<string, "success" | "warning" | "error" | "default"> = {
  present: "success",
  absent: "error",
  suspected: "warning",
  historical: "default",
  family: "default",
};

function CodingResultsTable({ codes }: { codes: CodedEntity[] }) {
  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
        <MedicalServicesOutlinedIcon fontSize="small" color="primary" />
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
          Coding step -- SNOMED codes written to patient graph
        </Typography>
        <Chip label={`${codes.length} codes`} size="small" color="primary" />
      </Stack>
      <Box
        sx={{
          border: "1px solid",
          borderColor: "divider",
          borderRadius: 1,
          overflowY: "auto",
          maxHeight: 400,
        }}
      >
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600, width: "28%" }}>SNOMED term</TableCell>
              <TableCell sx={{ fontWeight: 600, width: "12%" }}>Concept ID</TableCell>
              <TableCell sx={{ fontWeight: 600, width: "14%" }}>Tag</TableCell>
              <TableCell sx={{ fontWeight: 600, width: "12%" }}>Assertion</TableCell>
              <TableCell sx={{ fontWeight: 600, width: "24%" }}>Evidence</TableCell>
              <TableCell sx={{ fontWeight: 600, width: "5%" }}>Conf.</TableCell>
              <TableCell sx={{ fontWeight: 600, width: "5%" }}>Tier</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {codes.map((c, i) => (
              <TableRow key={i} hover>
                <TableCell sx={{ fontWeight: 500, fontSize: "0.78rem" }}>{c.term}</TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: "0.72rem", color: "text.secondary" }}>
                  {c.concept_id}
                </TableCell>
                <TableCell>
                  <Chip
                    label={c.semantic_tag || "unknown"}
                    color={tagColour(c.semantic_tag)}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: "0.68rem" }}
                  />
                </TableCell>
                <TableCell>
                  <Chip
                    label={c.assertion || "present"}
                    color={ASSERTION_COLOUR[c.assertion?.toLowerCase() ?? "present"] ?? "default"}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: "0.68rem" }}
                  />
                </TableCell>
                <TableCell sx={{ fontSize: "0.72rem", color: "text.secondary", fontStyle: "italic" }}>
                  {c.evidence || "-"}
                </TableCell>
                <TableCell sx={{ fontSize: "0.72rem" }}>
                  {c.confidence != null ? (c.confidence * 100).toFixed(0) + "%" : "-"}
                </TableCell>
                <TableCell sx={{ fontSize: "0.72rem" }}>{c.decision_tier || "-"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>
    </Box>
  );
}
