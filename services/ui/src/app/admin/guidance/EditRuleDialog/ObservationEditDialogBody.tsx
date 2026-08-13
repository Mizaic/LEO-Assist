/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-C21AE387 / DI-42246DA7
 *   DO: DO-AA74E9A6 / DO-F8C56339
 */
"use client";

/**
 * Operator / value / unit editor for measurable readings inside
 * ConceptSynonymDialog (OBSERVATION leaves, or observable CONCEPT
 * leaves the reviewer wants to turn into a reading comparison).
 */
import { useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import MultiConceptObsFields from "./MultiConceptObsFields";
import { MULTI_CONCEPT_PICKER, SYNONYM_OBSERVATION_EDIT } from "./copy";
import {
  DEFAULT_OBS_THRESHOLD,
  draftHasNumericValue,
  type ObservableThresholdDraft,
} from "./multiConceptSeed";
import type {
  EditableLogicNode,
  EditableObservationPayload,
  LogicSeed,
  NodeUpdate,
  ObservationOperator,
} from "./types";

function draftFromObservation(
  obs: EditableObservationPayload | undefined,
): ObservableThresholdDraft {
  if (!obs) return { ...DEFAULT_OBS_THRESHOLD };
  if (obs.operator === "between" && Array.isArray(obs.value)) {
    return {
      operator: "between",
      value: String(obs.value[0] ?? ""),
      value2: String(obs.value[1] ?? ""),
      unit: obs.unit ?? "",
    };
  }
  return {
    operator: (obs.operator ?? ">=") as ObservationOperator,
    value: obs.value != null ? String(obs.value) : "",
    value2: "",
    unit: obs.unit ?? "",
  };
}

export function observationPayloadFromDraft(
  observableId: string,
  observableTerm: string,
  draft: ObservableThresholdDraft,
): EditableObservationPayload | null {
  if (!draftHasNumericValue(draft)) return null;
  const lo = Number(draft.value);
  const unit = draft.unit.trim();
  if (draft.operator === "between") {
    const hi = Number(draft.value2);
    if (!Number.isFinite(hi)) return null;
    return {
      kind: "OBSERVATION",
      observable_id: observableId,
      observable_term: observableTerm,
      operator: "between",
      value: [lo, hi],
      unit,
      within_days: 365,
    };
  }
  return {
    kind: "OBSERVATION",
    observable_id: observableId,
    observable_term: observableTerm,
    operator: draft.operator,
    value: lo,
    unit,
    within_days: 365,
  };
}

interface Props {
  node: EditableLogicNode;
  primarySeed?: LogicSeed;
  onUpdate: (u: NodeUpdate) => void;
}

export default function ObservationEditDialogBody({
  node,
  primarySeed,
  onUpdate,
}: Props) {
  const existing = node.kind === "OBSERVATION" ? node.observation : undefined;
  const observableId =
    existing?.observable_id ?? primarySeed?.snomed_concept_id ?? "";
  const observableTerm =
    existing?.observable_term ?? primarySeed?.preferred_term ?? "this reading";

  const [draft, setDraft] = useState<ObservableThresholdDraft>(() =>
    draftFromObservation(existing),
  );

  const payload = useMemo(
    () => observationPayloadFromDraft(observableId, observableTerm, draft),
    [observableId, observableTerm, draft],
  );

  function applyDraft(next: ObservableThresholdDraft) {
    setDraft(next);
    const built = observationPayloadFromDraft(observableId, observableTerm, next);
    if (!built) return;
    if (node.kind === "OBSERVATION") {
      onUpdate({ kind: "set_observation", nodeId: node.node_id, observation: built });
      return;
    }
    onUpdate({
      kind: "convert_concept_to_observation",
      nodeId: node.node_id,
      observation: built,
    });
  }

  return (
    <Stack spacing={1.5}>
      <Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
          {SYNONYM_OBSERVATION_EDIT.heading}
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block">
          {MULTI_CONCEPT_PICKER.observationHint}
        </Typography>
      </Box>
      <MultiConceptObsFields
        term={observableTerm}
        observableId={observableId}
        draft={draft}
        onChange={applyDraft}
      />
      {payload && (
        <Typography variant="caption" color="success.main">
          {SYNONYM_OBSERVATION_EDIT.savedHint}
        </Typography>
      )}
      <Divider />
      <Typography variant="caption" color="text.secondary">
        {SYNONYM_OBSERVATION_EDIT.footerHint}
      </Typography>
    </Stack>
  );
}

export function observationUpdateFromDraft(
  node: EditableLogicNode,
  primarySeed: LogicSeed | undefined,
  draft: ObservableThresholdDraft,
): NodeUpdate | null {
  if (!draftHasNumericValue(draft)) return null;
  const observableId =
    node.kind === "OBSERVATION"
      ? node.observation?.observable_id ?? ""
      : primarySeed?.snomed_concept_id ?? "";
  const observableTerm =
    node.kind === "OBSERVATION"
      ? node.observation?.observable_term ?? ""
      : primarySeed?.preferred_term ?? "";
  const built = observationPayloadFromDraft(observableId, observableTerm, draft);
  if (!built) return null;
  if (node.kind === "OBSERVATION") {
    return { kind: "set_observation", nodeId: node.node_id, observation: built };
  }
  return {
    kind: "convert_concept_to_observation",
    nodeId: node.node_id,
    observation: built,
  };
}
