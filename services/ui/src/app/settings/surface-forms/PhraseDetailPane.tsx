/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useEffect, useState } from "react";
import { color, elevation } from "@leo/design-system/tokens";

import { SnomedPickConfirmDialog } from "@/components/SnomedPickConfirmDialog";

import type { UncodedPhrase } from "./phraseMappingsApi";
import type { SnomedPick } from "./PhraseSnomedPicker";
import { PhraseDetailHeader } from "./PhraseDetailHeader";
import { PhraseDetailSaveDock } from "./PhraseDetailSaveDock";
import { MappingEditor, ReviewSummary } from "./PhraseMappingEditor";
import { termNeedsFix } from "./termNeedsFix";

function restoreDraft(phrase: UncodedPhrase): {
  pick: SnomedPick | null;
  exclude: boolean;
  reason: string;
} {
  const reason = phrase.draft_reason || "";
  if (phrase.draft_action === "map" && phrase.draft_concept_id) {
    return {
      pick: {
        concept_id: phrase.draft_concept_id,
        term: phrase.draft_concept_term || "",
      },
      exclude: false,
      reason,
    };
  }
  return {
    pick: null,
    exclude: phrase.draft_action === "exclude",
    reason,
  };
}

type DetailMode = "inbox" | "drafts" | "review";

export function PhraseDetailPane({
  phrase,
  mode,
  onSave,
  onPublish,
  onSendBack,
  saving,
  error,
}: {
  phrase: UncodedPhrase;
  mode: DetailMode;
  onSave: (pick: SnomedPick | null, excludeReason: string) => void;
  onPublish?: () => void;
  onSendBack?: () => void;
  saving: boolean;
  error: string;
}) {
  const [pick, setPick] = useState<SnomedPick | null>(null);
  const [pending, setPending] = useState<SnomedPick | null>(null);
  const [exclude, setExclude] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    const next = restoreDraft(phrase);
    setPick(next.pick);
    setExclude(next.exclude);
    setReason(next.reason);
    setPending(null);
  }, [phrase]);

  const canSave = exclude
    ? reason.trim().length > 0
    : Boolean(pick?.concept_id) && !termNeedsFix(pick?.term, pick?.concept_id);

  return (
    <div
      data-testid="phrase-detail"
      style={{
        background: color.surface.raised,
        borderRadius: 16,
        boxShadow: elevation.card,
        padding: "22px 22px 0",
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minWidth: 0,
        minHeight: 0,
        maxWidth: "100%",
        overflow: "hidden",
        boxSizing: "border-box",
      }}
    >
      <div style={{ flex: 1, minHeight: 0, overflow: "auto", paddingBottom: 12 }}>
        <PhraseDetailHeader phrase={phrase} />
        {mode !== "review" ? (
          <MappingEditor
            phrase={phrase}
            pick={pick}
            exclude={exclude}
            reason={reason}
            handlers={{
              pendingId: pending?.concept_id || "",
              onPick: (next) => {
                setExclude(false);
                setPending(next);
              },
              onConfirmTerm: setPick,
              onExclude: () => {
                setExclude(true);
                setPick(null);
              },
              onReason: setReason,
            }}
          />
        ) : (
          <ReviewSummary phrase={phrase} />
        )}
        {error ? (
          <p style={{ color: color.status.danger, fontSize: 13, marginTop: 12 }}>
            {error}
          </p>
        ) : null}
      </div>
      <PhraseDetailSaveDock
        mode={mode}
        canSave={canSave}
        saving={saving}
        exclude={exclude}
        onSave={() => onSave(pick, reason)}
        onPublish={onPublish}
        onSendBack={onSendBack}
      />
      {pending ? (
        <SnomedPickConfirmDialog
          copy={{
            title: "Save this mapping draft?",
            lead:
              'Map "' +
              phrase.normalized +
              '" to this SNOMED code. Drafts do not change coding yet.',
            confirmLabel: "Save draft",
          }}
          pick={{
            term: pending.term,
            conceptId: pending.concept_id,
            tag: pending.semantic_tag,
          }}
          contextRows={[{ label: "Phrase", value: phrase.normalized }]}
          action={{
            busy: saving,
            onConfirm: () => {
              setPick(pending);
              setPending(null);
              onSave(pending, reason);
            },
            onCancel: () => setPending(null),
          }}
        />
      ) : null}
    </div>
  );
}
