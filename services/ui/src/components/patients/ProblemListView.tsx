/**
 * ProblemListView -- grouped coded-entity chips for the EPR shell.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468, DI-7DE8E8ED
 */
"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { CodedEntityRow } from "@/lib/patientEprApi";
import { CodedEntityChip } from "./CodedEntityChip";

const ENTITY_TYPE_LABEL: Record<string, string> = {
  disorder: "Conditions",
  disease: "Conditions",
  finding: "Clinical findings",
  situation: "Situations",
  observable: "Lab results",
  procedure: "Procedures",
  medication: "Medications",
  concept: "Other codes",
};

interface Props {
  patientId: string;
  entities: CodedEntityRow[];
  loading?: boolean;
  maxPerGroup?: number;
}

export function ProblemListView({
  patientId,
  entities,
  loading = false,
  maxPerGroup = 6,
}: Props) {
  if (loading) {
    return (
      <Stack spacing={0.75}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height={22} />
        ))}
      </Stack>
    );
  }

  if (entities.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" fontStyle="italic">
        No coded problems on record.
      </Typography>
    );
  }

  const grouped = entities.reduce<Record<string, CodedEntityRow[]>>((acc, e) => {
    const key = e.entity_type;
    if (!acc[key]) acc[key] = [];
    acc[key].push(e);
    return acc;
  }, {});

  return (
    <Stack spacing={1.5}>
      {Object.entries(grouped).map(([type, items]) => (
        <Box key={type}>
          <Typography
            variant="caption"
            fontWeight={700}
            color="text.secondary"
            sx={{
              textTransform: "uppercase",
              fontSize: 10,
              display: "block",
              mb: 0.5,
            }}
          >
            {ENTITY_TYPE_LABEL[type] ?? type}
          </Typography>
          <Stack direction="row" flexWrap="wrap" gap={0.5}>
            {items.slice(0, maxPerGroup).map((e, i) => (
              <CodedEntityChip
                key={`${e.name}-${i}`}
                patientId={patientId}
                name={e.name}
                conceptId={e.concept_id}
              />
            ))}
            {items.length > maxPerGroup && (
              <Chip
                label={`+${items.length - maxPerGroup} more`}
                size="small"
                sx={{ height: 20, fontSize: 10, bgcolor: "#E2E8F0", color: "#64748B" }}
              />
            )}
          </Stack>
        </Box>
      ))}
    </Stack>
  );
}
