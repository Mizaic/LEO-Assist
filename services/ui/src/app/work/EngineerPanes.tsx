/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useAuth } from "@/lib/authContext";
import { getFailureCopy } from "./failureCopy";
import { ActiveFixForm } from "./WorkFixForms";
import type { UncodedPhrase, WorkFixKind } from "./workFixApi";

export type EngineerStep = "debug" | "fix" | "review" | "deploy";

export function extractorCopy(source: string | undefined): string {
  const key = (source || "").trim().toLowerCase();
  if (key === "llm") return "Found by the language model (LLM).";
  if (key === "model" || key === "ner" || key === "ner_lab_fallback") {
    return "Found by named-entity recognition (NER).";
  }
  return "";
}

export function statusCopy(status: string | undefined): string {
  if (status === "draft") return "A draft is saved. It is not live yet.";
  if (status === "review") return "Waiting for a different person to publish.";
  if (status === "closed") return "This phrase is already live.";
  return "This phrase is not mapped yet.";
}

const DEBUG_LETTER_LIMIT = 280;

export function debugLetterSample(sample: string): string {
  const text = sample.trim();
  if (!text) return "";
  if (text.length > DEBUG_LETTER_LIMIT) return "See the letter on the left.";
  return `In the letter: ${text}`;
}

export function EngineerStepBar({
  step,
  onSelect,
}: {
  step: EngineerStep;
  onSelect: (step: EngineerStep) => void;
}) {
  const items: Array<[EngineerStep, string]> = [
    ["debug", "Debug"],
    ["fix", "Fix"],
    ["review", "Review"],
    ["deploy", "Deploy"],
  ];
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {items.map(([id, label]) => (
        <Button
          key={id}
          size="small"
          variant={step === id ? "contained" : "outlined"}
          onClick={() => onSelect(id)}
        >
          {label}
        </Button>
      ))}
    </Stack>
  );
}

export function DebugPane({
  row,
  encounterText,
  failureKind,
}: {
  row: UncodedPhrase | null;
  encounterText?: string;
  failureKind?: string;
}) {
  const sample = row?.sample_sentence || encounterText || "";
  const letterHint = debugLetterSample(sample);
  const foundBy = extractorCopy(row?.last_extractor);
  const copy = getFailureCopy(failureKind);
  return (
    <Stack spacing={0.75}>
      {copy.headline ? (
        <Typography variant="body2" fontWeight="medium">
          {copy.headline}
        </Typography>
      ) : null}
      {copy.detail ? (
        <Typography variant="caption" color="text.secondary">
          {copy.detail}
        </Typography>
      ) : null}
      <Typography variant="body2">{statusCopy(row?.status)}</Typography>
      {foundBy ? (
        <Typography variant="caption" color="text.secondary">
          {foundBy}
        </Typography>
      ) : null}
      {row?.last_best_term ? (
        <Typography variant="caption" color="text.secondary">
          Closest code so far: {row.last_best_term}
        </Typography>
      ) : null}
      {letterHint ? (
        <Typography variant="caption" color="text.secondary">
          {letterHint}
        </Typography>
      ) : null}
      {row?.draft_action === "map" && row.draft_concept_term ? (
        <Typography variant="caption">
          Draft map: {row.draft_concept_term}
        </Typography>
      ) : null}
      {row?.draft_action === "exclude" && row.draft_reason ? (
        <Typography variant="caption">Draft exclude: {row.draft_reason}</Typography>
      ) : null}
    </Stack>
  );
}

export function ReviewPane({
  row,
  busy,
  onSubmit,
}: {
  row: UncodedPhrase | null;
  busy: boolean;
  onSubmit: () => void;
}) {
  const ready = row?.status === "draft";
  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        Submit sends this draft to review. It does not change live coding yet.
      </Typography>
      <Button
        size="small"
        variant="contained"
        disabled={busy || !ready}
        onClick={onSubmit}
      >
        {busy ? "Submitting..." : "Submit for review"}
      </Button>
      {!ready ? (
        <Typography variant="caption" color="text.secondary">
          Save a fix first, then submit.
        </Typography>
      ) : null}
    </Stack>
  );
}

export function DeployPane({
  row,
  busy,
  onDeploy,
}: {
  row: UncodedPhrase | null;
  busy: boolean;
  onDeploy: () => void;
}) {
  const { session } = useAuth();
  const ready = row?.status === "review";
  const currentEmail = (session?.user.email ?? "").toLowerCase();
  const draftAuthor = (row?.draft_author ?? "").toLowerCase();
  const isAuthor = Boolean(currentEmail && currentEmail === draftAuthor);
  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.secondary">
        A different person must publish. That is what makes the fix live.
      </Typography>
      <Button
        size="small"
        variant="contained"
        disabled={busy || !ready || isAuthor}
        onClick={onDeploy}
      >
        {busy ? "Publishing..." : "Publish to live"}
      </Button>
      {isAuthor && ready ? (
        <Typography variant="caption" color="text.secondary">
          You drafted this change. A different person must publish it.
        </Typography>
      ) : null}
      {!ready && !isAuthor ? (
        <Typography variant="caption" color="text.secondary">
          Submit for review before anyone can publish.
        </Typography>
      ) : null}
    </Stack>
  );
}

export function EngineerHeader() {
  return (
    <div>
      <Typography variant="subtitle2">Engineer panel</Typography>
      <Typography variant="caption" color="text.secondary">
        Debug, fix, submit for review, then a different person deploys.
      </Typography>
    </div>
  );
}

export function EngineerBody(props: {
  step: EngineerStep;
  mode: WorkFixKind | "idle";
  phrase: string;
  entityText: string;
  entityLabel?: string;
  reviewId?: string | null;
  encounterText?: string;
  contextPhrase: string;
  category: string;
  direction: string;
  busy: boolean;
  row: UncodedPhrase | null;
  failureKind?: string;
  onSelectMode: (mode: WorkFixKind) => void;
  onContextPhraseChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onDirectionChange: (value: string) => void;
  onIdle: () => void;
  onRunFix: (kind: WorkFixKind, action: () => Promise<void>) => Promise<void>;
  onSubmit: () => void;
  onDeploy: () => void;
}) {
  if (props.step === "debug") {
    return (
      <DebugPane
        row={props.row}
        encounterText={props.encounterText}
        failureKind={props.failureKind}
      />
    );
  }
  if (props.step === "review") {
    return (
      <ReviewPane row={props.row} busy={props.busy} onSubmit={props.onSubmit} />
    );
  }
  if (props.step === "deploy") {
    return (
      <DeployPane row={props.row} busy={props.busy} onDeploy={props.onDeploy} />
    );
  }
  return <FixPane {...props} />;
}

function FixPane(props: {
  mode: WorkFixKind | "idle";
  phrase: string;
  entityText: string;
  entityLabel?: string;
  reviewId?: string | null;
  encounterText?: string;
  contextPhrase: string;
  category: string;
  direction: string;
  busy: boolean;
  failureKind?: string;
  onSelectMode: (mode: WorkFixKind) => void;
  onContextPhraseChange: (value: string) => void;
  onCategoryChange: (value: string) => void;
  onDirectionChange: (value: string) => void;
  onIdle: () => void;
  onRunFix: (kind: WorkFixKind, action: () => Promise<void>) => Promise<void>;
}) {
  const { recommendedFix } = getFailureCopy(props.failureKind);
  return (
    <>
      <ActionButtons
        mode={props.mode}
        onSelect={props.onSelectMode}
        recommendedFix={recommendedFix}
      />
      <ActiveFixForm
        mode={props.mode}
        phrase={props.phrase}
        entityText={props.entityText}
        entityLabel={props.entityLabel}
        reviewId={props.reviewId}
        encounterText={props.encounterText}
        contextPhrase={props.contextPhrase}
        category={props.category}
        direction={props.direction}
        busy={props.busy}
        onContextPhraseChange={props.onContextPhraseChange}
        onCategoryChange={props.onCategoryChange}
        onDirectionChange={props.onDirectionChange}
        onIdle={props.onIdle}
        onRunFix={props.onRunFix}
      />
    </>
  );
}

function ActionButtons({
  mode,
  onSelect,
  recommendedFix,
}: {
  mode: WorkFixKind | "idle";
  onSelect: (mode: WorkFixKind) => void;
  recommendedFix?: WorkFixKind | null;
}) {
  const isActive = (kind: WorkFixKind) => mode === kind;
  const isRecommended = (kind: WorkFixKind) =>
    recommendedFix === kind && mode === "idle";
  const variant = (kind: WorkFixKind) =>
    isActive(kind) || isRecommended(kind) ? "contained" : "outlined";
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Button
        size="small"
        variant={variant("map")}
        onClick={() => onSelect("map")}
        aria-label={
          isRecommended("map") ? "Map this phrase (recommended)" : "Map this phrase"
        }
      >
        Map this phrase
      </Button>
      <Button
        size="small"
        variant={variant("exclude")}
        onClick={() => onSelect("exclude")}
        aria-label={
          isRecommended("exclude")
            ? "Do not code this (recommended)"
            : "Do not code this"
        }
      >
        Do not code this
      </Button>
      <Button
        size="small"
        variant={variant("context")}
        onClick={() => onSelect("context")}
        aria-label={
          isRecommended("context")
            ? "Add a context cue (recommended)"
            : "Add a context cue"
        }
      >
        Add a context cue
      </Button>
      <Button
        size="small"
        variant={variant("teach")}
        onClick={() => onSelect("teach")}
        aria-label={
          isRecommended("teach")
            ? "Teach the extractor (recommended)"
            : "Teach the extractor"
        }
      >
        Teach the extractor
      </Button>
    </Stack>
  );
}
