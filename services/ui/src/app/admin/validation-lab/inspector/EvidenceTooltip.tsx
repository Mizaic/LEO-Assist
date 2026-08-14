/**
 * Structured evidence tooltip for Validation Lab fact chips.
 *
 * Atlas: DI-257D6883 / DO-158BE606 / VT-825F42CC
 */
"use client";

import type { ReactElement } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import type { LabWorkItem } from "../inspectorTypes";
import { assertionLabel, semanticTagLabel } from "../letterMarkStyle";
import { plainLetterText } from "./stageWorkItems";

const PANEL_SX = {
  bgcolor: "#0F172A",
  color: "#F8FAFC",
  border: "1px solid #334155",
  maxWidth: 560,
} as const;

export function EvidenceTooltip({
  item,
  children,
}: {
  item: LabWorkItem;
  children: ReactElement;
}) {
  return (
    <Tooltip
      disableInteractive={false}
      enterDelay={250}
      leaveDelay={200}
      placement="top"
      slotProps={{ tooltip: { sx: PANEL_SX } }}
      title={<EvidenceTooltipBody item={item} />}
    >
      {children}
    </Tooltip>
  );
}

export function EvidenceTooltipBody({ item }: { item: LabWorkItem }) {
  const title = plainLetterText(item.text);
  const mention = plainLetterText(item.evidence || "");
  const sentence = plainLetterText(item.evidenceSentence || "");
  const showMention = Boolean(
    mention && mention.toLowerCase() !== title.toLowerCase(),
  );
  const measurement = [item.value, item.unit].filter(Boolean).join(" ");
  return (
    <Stack spacing={1.25} data-testid="validation-lab-evidence-tooltip">
      <Box>
        <Typography sx={{ fontWeight: 700, fontSize: "0.8rem", color: "#F8FAFC" }}>
          {title}
        </Typography>
        {item.code ? (
          <Typography sx={{ mt: 0.25, fontSize: "0.72rem", color: "#CBD5E1" }}>
            Code {item.code}
          </Typography>
        ) : null}
      </Box>
      {item.relationType && item.relationTarget ? (
        <TooltipBlock label={item.relationType} body={item.relationTarget} />
      ) : null}
      {measurement ? (
        <TooltipBlock label="Measurement" body={measurement} />
      ) : null}
      {item.referenceRange ? (
        <TooltipBlock label="Reference range" body={item.referenceRange} />
      ) : null}
      {item.assertion ? (
        <TooltipBlock label="Context" body={assertionLabel(item.assertion)} />
      ) : null}
      {item.semanticTag ? (
        <TooltipBlock label="Kind" body={semanticTagLabel(item.semanticTag)} />
      ) : null}
      {showMention ? <TooltipBlock label="Words found" body={mention} /> : null}
      {sentence ? <TooltipBlock label="From the letter" body={sentence} /> : null}
    </Stack>
  );
}

function TooltipBlock({ label, body }: { label: string; body: string }) {
  return (
    <Box>
      <Typography
        sx={{
          fontSize: "0.68rem",
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: "#94A3B8",
          mb: 0.4,
        }}
      >
        {label}
      </Typography>
      <Typography sx={{ fontSize: "0.78rem", lineHeight: 1.5, color: "#F8FAFC" }}>
        {body}
      </Typography>
    </Box>
  );
}
