/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useEffect, useState } from "react";

import { searchTerms } from "@/lib/api/legacy";

import type { SnomedPick } from "./PhraseSnomedPicker";
import { termNeedsFix } from "./termNeedsFix";

export function DraftMappingCard({
  pick,
  extractedTag,
  onConfirm,
}: {
  pick: SnomedPick;
  extractedTag: string;
  onConfirm: (next: SnomedPick) => void;
}) {
  const needsFix = termNeedsFix(pick.term, pick.concept_id);
  return (
    <div
      data-testid="draft-mapping"
      style={{
        margin: "0 0 12px",
        padding: 14,
        border: needsFix ? "2px solid #C2410C" : "2px solid #1D4ED8",
        background: needsFix ? "#FFF7ED" : "#EFF6FF",
        borderRadius: 14,
      }}
    >
      <p
        style={{
          margin: 0,
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
          color: needsFix ? "#9A3412" : "#1E40AF",
        }}
      >
        {needsFix ? "Code saved -- preferred term missing" : "Your mapping"}
      </p>
      <strong style={{ display: "block", marginTop: 6, fontSize: 16 }}>
        {needsFix ? pick.concept_id : pick.term || pick.concept_id}
      </strong>
      {needsFix ? null : (
        <span style={{ display: "block", marginTop: 4, fontSize: 13, color: "#596577" }}>
          {pick.concept_id}
          {pick.semantic_tag ? ` · ${pick.semantic_tag}` : ""}
        </span>
      )}
      {needsFix ? (
        <TermFixBanner
          conceptId={pick.concept_id}
          extractedTag={extractedTag}
          onConfirm={onConfirm}
        />
      ) : null}
    </div>
  );
}

function TermFixBanner({
  conceptId,
  extractedTag,
  onConfirm,
}: {
  conceptId: string;
  extractedTag: string;
  onConfirm: (next: SnomedPick) => void;
}) {
  const [suggestion, setSuggestion] = useState<SnomedPick | null>(null);
  const [busy, setBusy] = useState(true);
  const [lookupError, setLookupError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    setLookupError("");
    setSuggestion(null);
    void lookupPreferredTerm(conceptId).then((result) => {
      if (cancelled) return;
      setBusy(false);
      if (result.ok) {
        setSuggestion(result.pick);
        return;
      }
      setLookupError(result.error);
    });
    return () => {
      cancelled = true;
    };
  }, [conceptId]);

  if (busy) {
    return (
      <p style={{ margin: "10px 0 0", fontSize: 13, color: "#9A3412" }}>
        Looking up preferred term.
      </p>
    );
  }
  if (lookupError || !suggestion) {
    return (
      <p style={{ margin: "10px 0 0", fontSize: 13, color: "#9A3412" }}>
        {lookupError || "Could not find a preferred term. Search SNOMED below."}
      </p>
    );
  }
  return (
    <SuggestedTerm
      suggestion={suggestion}
      extractedTag={extractedTag}
      onConfirm={onConfirm}
    />
  );
}

async function lookupPreferredTerm(
  conceptId: string,
): Promise<{ ok: true; pick: SnomedPick } | { ok: false; error: string }> {
  try {
    const hits = await searchTerms(conceptId, 5);
    const match = hits.find((hit) => hit.snomed_concept_id === conceptId);
    if (match?.term && !termNeedsFix(match.term, match.snomed_concept_id)) {
      return {
        ok: true,
        pick: {
          concept_id: match.snomed_concept_id,
          term: match.term,
          semantic_tag: match.semantic_tag,
        },
      };
    }
    return {
      ok: false,
      error: "Could not find a preferred term. Search SNOMED below.",
    };
  } catch {
    return {
      ok: false,
      error: "Could not look up this code. Search SNOMED below.",
    };
  }
}

function SuggestedTerm({
  suggestion,
  extractedTag,
  onConfirm,
}: {
  suggestion: SnomedPick;
  extractedTag: string;
  onConfirm: (next: SnomedPick) => void;
}) {
  const tagMismatch =
    extractedTag &&
    suggestion.semantic_tag &&
    extractedTag.toLowerCase() !== suggestion.semantic_tag.toLowerCase();
  return (
    <div data-testid="preferred-term-fix" style={{ marginTop: 12 }}>
      <p style={{ margin: 0, fontSize: 13, color: "#9A3412" }}>
        Official name: <strong>{suggestion.term}</strong>
        {suggestion.semantic_tag ? ` (${suggestion.semantic_tag})` : ""}
        {tagMismatch ? ". This type differs from extraction." : ""}
      </p>
      <button
        type="button"
        onClick={() => onConfirm(suggestion)}
        style={{
          marginTop: 10,
          height: 40,
          padding: "0 14px",
          border: 0,
          borderRadius: 10,
          background: "#C2410C",
          color: "#fff",
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        Use this preferred term
      </button>
    </div>
  );
}
