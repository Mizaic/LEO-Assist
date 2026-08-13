/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useEffect, useState } from "react";

import type { UncodedPhrase } from "./phraseMappingsApi";
import { PhraseSnomedPicker, type SnomedPick } from "./PhraseSnomedPicker";
import { DraftMappingCard } from "./DraftMappingCard";
import { termNeedsFix } from "./termNeedsFix";

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (ch) => {
    const map: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return map[ch] || ch;
  });
}

function highlight(sentence: string, span: string): string {
  const text = sentence || "";
  const safe = escapeHtml(text);
  if (!span) return safe;
  const idx = text.toLowerCase().indexOf(span.toLowerCase());
  if (idx < 0) return safe;
  const before = escapeHtml(text.slice(0, idx));
  const match = escapeHtml(text.slice(idx, idx + span.length));
  const after = escapeHtml(text.slice(idx + span.length));
  return `${before}<strong>${match}</strong>${after}`;
}

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
  const [exclude, setExclude] = useState(false);
  const [reason, setReason] = useState("");

  useEffect(() => {
    const next = restoreDraft(phrase);
    setPick(next.pick);
    setExclude(next.exclude);
    setReason(next.reason);
  }, [phrase]);

  const canSave = exclude
    ? reason.trim().length > 0
    : Boolean(pick?.concept_id) && !termNeedsFix(pick?.term, pick?.concept_id);

  return (
    <div
      data-testid="phrase-detail"
      style={{
        background: "#fff",
        borderRadius: 16,
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
        <PhraseHeader phrase={phrase} />
        {mode !== "review" ? (
          <MappingEditor
            phrase={phrase}
            pick={pick}
            exclude={exclude}
            reason={reason}
            onPick={(next) => {
              setExclude(false);
              setPick(next);
            }}
            onExclude={() => {
              setExclude(true);
              setPick(null);
            }}
            onReason={setReason}
          />
        ) : (
          <ReviewSummary phrase={phrase} />
        )}
        {error ? (
          <p style={{ color: "#B91C1C", fontSize: 13, marginTop: 12 }}>{error}</p>
        ) : null}
      </div>
      <SaveDock
        mode={mode}
        canSave={canSave}
        saving={saving}
        exclude={exclude}
        onSave={() => onSave(pick, reason)}
        onPublish={onPublish}
        onSendBack={onSendBack}
      />
    </div>
  );
}

function PhraseHeader({ phrase }: { phrase: UncodedPhrase }) {
  const scorePct =
    phrase.last_score != null ? Math.round(Number(phrase.last_score) * 100) : null;
  const tagMismatch =
    phrase.extracted_tag &&
    phrase.last_best_tag &&
    phrase.extracted_tag.toLowerCase() !== phrase.last_best_tag.toLowerCase();
  return (
    <>
      <p
        style={{
          margin: 0,
          fontSize: 12,
          fontWeight: 600,
          color: "#6B7280",
          textTransform: "uppercase",
          letterSpacing: "0.04em",
        }}
      >
        Pipeline rejected
      </p>
      <h2
        style={{
          margin: "4px 0 0",
          fontSize: 24,
          lineHeight: 1.12,
          fontWeight: 700,
          overflowWrap: "anywhere",
        }}
      >
        {phrase.normalized}
      </h2>
      {phrase.sample_sentence ? (
        <p
          style={{
            margin: "14px 0",
            padding: "12px 14px",
            borderRadius: 10,
            background: "#F2F2F7",
            color: "#596577",
            fontSize: 14,
          }}
          dangerouslySetInnerHTML={{
            __html: highlight(
              phrase.sample_sentence,
              phrase.sample_span || phrase.normalized,
            ),
          }}
        />
      ) : null}
      <PhraseFacts
        phrase={phrase}
        scorePct={scorePct}
        tagMismatch={Boolean(tagMismatch)}
      />
    </>
  );
}

function MappingEditor({
  phrase,
  pick,
  exclude,
  reason,
  onPick,
  onExclude,
  onReason,
}: {
  phrase: UncodedPhrase;
  pick: SnomedPick | null;
  exclude: boolean;
  reason: string;
  onPick: (next: SnomedPick) => void;
  onExclude: () => void;
  onReason: (value: string) => void;
}) {
  return (
    <>
      <p
        style={{
          margin: "18px 0 8px",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: "#6B7280",
        }}
      >
        Map to a code
      </p>
      {pick && !exclude ? (
        <DraftMappingCard
          pick={pick}
          extractedTag={phrase.extracted_tag}
          onConfirm={onPick}
        />
      ) : null}
      <PhraseSnomedPicker
        key={phrase.phrase_key}
        phrase={phrase}
        pickedId={pick?.concept_id || ""}
        hasSavedPick={Boolean(pick?.concept_id)}
        onPick={onPick}
      />
      <ExcludeBox
        exclude={exclude}
        reason={reason}
        onToggle={onExclude}
        onReason={onReason}
      />
    </>
  );
}

function PhraseFacts({
  phrase,
  scorePct,
  tagMismatch,
}: {
  phrase: UncodedPhrase;
  scorePct: number | null;
  tagMismatch: boolean;
}) {
  const chips = [
    phrase.extracted_tag ? `Extraction tag: ${phrase.extracted_tag}` : "",
    scorePct != null ? `Best score: ${scorePct}%` : "",
    phrase.last_best_term
      ? `Best match: ${phrase.last_best_term}${phrase.last_best_tag ? ` (${phrase.last_best_tag})` : ""}`
      : "",
  ].filter(Boolean);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
      {chips.map((label) => (
        <span
          key={label}
          style={{
            background: tagMismatch && label.startsWith("Extraction") ? "#FEF3C7" : "#F2F2F7",
            color: tagMismatch && label.startsWith("Extraction") ? "#92400E" : "#596577",
            borderRadius: 999,
            padding: "4px 10px",
            fontSize: 12,
          }}
        >
          {label}
        </span>
      ))}
    </div>
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
  return (
    <div style={{ marginTop: 12 }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          display: "block",
          width: "100%",
          textAlign: "left",
          border: exclude ? "2px solid #B91C1C" : "2px solid rgba(15, 23, 42, 0.08)",
          background: exclude ? "#FEF2F2" : "#fff",
          borderRadius: 14,
          padding: 14,
          cursor: "pointer",
        }}
      >
        <strong style={{ display: "block", fontSize: 16 }}>Do not code this phrase</strong>
        <span style={{ display: "block", marginTop: 4, fontSize: 13, color: "#596577" }}>
          Exclude is harder than map. It needs a reason and a second person to publish.
        </span>
      </button>
      {exclude ? (
        <textarea
          value={reason}
          onChange={(e) => onReason(e.target.value)}
          placeholder="Why should LEO skip this phrase?"
          aria-label="Exclude reason"
          style={{
            width: "100%",
            marginTop: 10,
            minHeight: 72,
            border: 0,
            borderRadius: 10,
            padding: "10px 12px",
            background: "#F2F2F7",
            fontSize: 15,
          }}
        />
      ) : null}
    </div>
  );
}

function ReviewSummary({ phrase }: { phrase: UncodedPhrase }) {
  const action = phrase.draft_action === "exclude" ? "Exclude" : "Map";
  return (
    <div
      style={{
        marginTop: 16,
        padding: 12,
        borderRadius: 10,
        background: "#FFFBEB",
        color: "#92400E",
        fontSize: 14,
      }}
    >
      <p style={{ margin: 0 }}>
        {action}
        {phrase.draft_concept_term ? `: ${phrase.draft_concept_term}` : ""}. Drafted by{" "}
        {phrase.draft_author || "unknown"}.
      </p>
      {phrase.draft_reason ? (
        <p style={{ margin: "8px 0 0" }}>{phrase.draft_reason}</p>
      ) : null}
    </div>
  );
}

function SaveDock({
  mode,
  canSave,
  saving,
  exclude,
  onSave,
  onPublish,
  onSendBack,
}: {
  mode: "inbox" | "drafts" | "review";
  canSave: boolean;
  saving: boolean;
  exclude: boolean;
  onSave: () => void;
  onPublish?: () => void;
  onSendBack?: () => void;
}) {
  return (
    <div
      data-testid="phrase-save-dock"
      style={{
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 12,
        margin: "0 -22px 0",
        padding: "12px 22px 16px",
        borderTop: "1px solid rgba(15, 23, 42, 0.08)",
        background: "rgba(255,255,255,0.92)",
      }}
    >
      <span style={{ marginRight: "auto", fontSize: 13, color: "#6B7280" }}>
        Drafts do not change coding yet.
      </span>
      {mode === "review" ? (
        <>
          <button type="button" onClick={onSendBack} disabled={saving}>
            Send back
          </button>
          <button
            type="button"
            onClick={onPublish}
            disabled={saving}
            style={{
              minWidth: 168,
              padding: "10px 18px",
              border: 0,
              borderRadius: 10,
              background: "#1D4ED8",
              color: "#fff",
              fontWeight: 600,
            }}
          >
            Publish
          </button>
        </>
      ) : (
        <button
          type="button"
          onClick={onSave}
          disabled={!canSave || saving}
          style={{
            minWidth: 168,
            padding: "10px 18px",
            border: 0,
            borderRadius: 10,
            background: exclude ? "#B91C1C" : "#1D4ED8",
            color: "#fff",
            fontWeight: 600,
            opacity: !canSave || saving ? 0.4 : 1,
          }}
        >
          {saving ? "Saving" : exclude ? "Save exclude draft" : "Save mapping draft"}
        </button>
      )}
    </div>
  );
}
