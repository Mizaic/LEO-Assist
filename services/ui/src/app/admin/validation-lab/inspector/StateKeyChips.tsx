/**
 * Key chips for Validation Lab pipeline stage input/output.
 *
 * Present keys are green. Hover or focus shows the stored value.
 * Entity lists expand into fact / SNOMED chips.
 *
 * Atlas trace:
 *   UN: UN-4DCE95C8
 *   DI: DI-FE423B8D, DI-257D6883
 *   DO: DO-158BE606
 *   VT: VT-C9851641, VT-825F42CC
 */
"use client";

import type { ReactElement } from "react";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { EvidenceTooltip } from "./EvidenceTooltip";
import { formatKeyTooltip, isPresentValue } from "./stateKeyPresence";
import {
  isEntityList,
  itemsFromEntities,
  sentenceList,
} from "./stageWorkItems";

interface Props {
  keys: string[];
  values: Record<string, unknown> | null;
  valuesReady: boolean;
}

const CHIP_SX = {
  height: 20,
  fontSize: "0.68rem",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
} as const;

const PRESENT_SX = {
  ...CHIP_SX,
  bgcolor: "#DCFCE7",
  color: "#166534",
  border: "1px solid #BBF7D0",
} as const;

const TOOLTIP_SX = {
  bgcolor: "#0F172A",
  color: "#F8FAFC",
  border: "1px solid #334155",
  maxWidth: 560,
  maxHeight: "calc(100vh - 16px)",
  overflow: "auto",
  p: 1.25,
} as const;

const POPPER_MODIFIERS = [
  {
    name: "preventOverflow",
    options: { altAxis: true, boundary: "viewport", padding: 8 },
  },
  {
    name: "flip",
    options: { fallbackPlacements: ["top", "bottom", "left", "right"] },
  },
];

export function StateKeyChips({ keys, values, valuesReady }: Props) {
  return (
    <Stack direction="row" flexWrap="wrap" gap={0.75}>
      {keys.map((key) => (
        <KeyChip
          key={key}
          name={key}
          value={values ? values[key] : undefined}
          sentences={values ? sentenceList(values) : []}
          ready={valuesReady}
        />
      ))}
    </Stack>
  );
}

function KeyChip({
  name,
  value,
  sentences,
  ready,
}: {
  name: string;
  value: unknown;
  sentences: unknown[];
  ready: boolean;
}) {
  const present = ready && isPresentValue(value);
  const expandFacts =
    name === "entities" || name === "resolved_entities";
  const entities =
    present && expandFacts && Array.isArray(value) && isEntityList(value)
      ? itemsFromEntities(value, sentences).slice(0, 8)
      : [];
  return (
    <>
      <ValueTooltip text={formatKeyTooltip(value, ready, sentences)}>
        <Chip
          label={name}
          size="small"
          tabIndex={0}
          variant={present ? "filled" : "outlined"}
          aria-label={`${name}: ${present ? "has a value" : ready ? "empty" : "not loaded yet"}`}
          data-present={present ? "true" : "false"}
          sx={present ? PRESENT_SX : CHIP_SX}
        />
      </ValueTooltip>
      {entities.map((item, index) => (
        <EvidenceTooltip key={`${item.text}-${index}`} item={item}>
          <Chip
            size="small"
            label={item.code ? `${item.text} -- ${item.code}` : item.text}
            aria-label={item.code ? `${item.text} code ${item.code}` : item.text}
            data-testid="validation-lab-entity-chip"
            sx={{ ...PRESENT_SX, fontFamily: "inherit" }}
          />
        </EvidenceTooltip>
      ))}
    </>
  );
}

function ValueTooltip({
  text,
  children,
}: {
  text: string;
  children: ReactElement;
}) {
  return (
    <Tooltip
      disableInteractive={false}
      enterDelay={250}
      leaveDelay={200}
      placement="top"
      slotProps={{
        tooltip: { sx: TOOLTIP_SX },
        popper: { modifiers: POPPER_MODIFIERS },
      }}
      title={
        <Typography
          component="pre"
          variant="caption"
          sx={{
            m: 0,
            color: "#F8FAFC",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        >
          {text}
        </Typography>
      }
    >
      {children}
    </Tooltip>
  );
}
