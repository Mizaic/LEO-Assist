/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { motion as fm } from "framer-motion";
import {
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

import type { UncodedPhrase } from "./phraseMappingsApi";
import { PhraseSnomedPicker, type SnomedPick } from "./PhraseSnomedPicker";
import { DraftMappingCard } from "./DraftMappingCard";

export function MappingEditor({
  phrase,
  pick,
  exclude,
  reason,
  handlers,
}: {
  phrase: UncodedPhrase;
  pick: SnomedPick | null;
  exclude: boolean;
  reason: string;
  handlers: {
    pendingId: string;
    onPick: (next: SnomedPick) => void;
    onConfirmTerm: (next: SnomedPick) => void;
    onExclude: () => void;
    onReason: (value: string) => void;
  };
}) {
  return (
    <>
      <p
        style={{
          margin: "18px 0 8px",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: typography.letterSpacing.caption,
          textTransform: "uppercase",
          color: color.text.caption,
        }}
      >
        Map to a code
      </p>
      {pick && !exclude ? (
        <DraftMappingCard
          pick={pick}
          extractedTag={phrase.extracted_tag}
          onConfirm={handlers.onConfirmTerm}
        />
      ) : null}
      <PhraseSnomedPicker
        key={phrase.phrase_key}
        phrase={phrase}
        pickedId={handlers.pendingId || pick?.concept_id || ""}
        hasSavedPick={Boolean(pick?.concept_id)}
        onPick={handlers.onPick}
      />
      <ExcludeBox
        exclude={exclude}
        reason={reason}
        onToggle={handlers.onExclude}
        onReason={handlers.onReason}
      />
    </>
  );
}

function ExcludeBox({
  exclude,
  reason,
  onToggle,
  onReason,
}: {
  exclude: boolean;
  reason: string;
  onToggle: () => void;
  onReason: (value: string) => void;
}) {
  const { reducedMotion } = useMotion();
  return (
    <div style={{ marginTop: 12 }}>
      <fm.button
        type="button"
        onClick={onToggle}
        whileTap={tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={excludeBtnStyle(exclude)}
      >
        <strong style={{ display: "block", fontSize: 16 }}>Do not code this phrase</strong>
        <span style={{ display: "block", marginTop: 4, fontSize: 13, color: color.text.secondary }}>
          Exclude is harder than map. It needs a reason and a second person to publish.
        </span>
      </fm.button>
      {exclude ? (
        <textarea
          value={reason}
          onChange={(e) => onReason(e.target.value)}
          placeholder="Why should LEO skip this phrase?"
          aria-label="Exclude reason"
          style={reasonStyle()}
        />
      ) : null}
    </div>
  );
}

export function ReviewSummary({ phrase }: { phrase: UncodedPhrase }) {
  const action = phrase.draft_action === "exclude" ? "Exclude" : "Map";
  return (
    <div
      style={{
        marginTop: 16,
        padding: 12,
        borderRadius: 10,
        background: "rgba(180, 83, 9, 0.08)",
        color: color.status.warning,
        fontSize: 14,
      }}
    >
      <p style={{ margin: 0 }}>
        {action}
        {phrase.draft_concept_term ? ": " + phrase.draft_concept_term : ""}. Drafted by{" "}
        {phrase.draft_author || "unknown"}.
      </p>
      {phrase.draft_reason ? (
        <p style={{ margin: "8px 0 0" }}>{phrase.draft_reason}</p>
      ) : null}
    </div>
  );
}

function excludeBtnStyle(exclude: boolean) {
  return {
    display: "block" as const,
    width: "100%",
    textAlign: "left" as const,
    border: exclude
      ? "2px solid " + color.status.danger
      : "2px solid " + color.text.secondary,
    background: exclude ? "rgba(185, 28, 28, 0.06)" : color.surface.raised,
    borderRadius: 14,
    padding: 14,
    cursor: "pointer" as const,
    fontFamily: typography.fontFamily.body,
  };
}

function reasonStyle() {
  return {
    width: "100%",
    marginTop: 10,
    minHeight: 72,
    border: "1px solid " + color.text.secondary,
    borderRadius: 10,
    padding: "10px 12px",
    background: color.surface.raised,
    color: color.text.primary,
    fontSize: 15,
    fontFamily: typography.fontFamily.body,
  };
}
