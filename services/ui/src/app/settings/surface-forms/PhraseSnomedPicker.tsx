/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useState, type CSSProperties } from "react";

import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import type { TermSearchResult } from "@/lib/types";

import type { UncodedPhrase } from "./phraseMappingsApi";

export interface SnomedPick {
  concept_id: string;
  term: string;
  semantic_tag?: string;
  leo?: boolean;
  reason?: string;
}

function toCandidate(row: TermSearchResult) {
  return {
    snomed_concept_id: row.snomed_concept_id,
    preferred_term: row.term,
    semantic_tag: row.semantic_tag || "",
    score: row.score ?? 0,
  };
}

export function PhraseSnomedPicker({
  phrase,
  onPick,
  pickedId,
  hasSavedPick = false,
}: {
  phrase: UncodedPhrase;
  onPick: (pick: SnomedPick) => void;
  pickedId: string;
  hasSavedPick?: boolean;
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<TermSearchResult[]>([]);
  const [didSearch, setDidSearch] = useState(false);
  const [busy, setBusy] = useState(false);
  const [leoReason, setLeoReason] = useState("");
  const [leoId, setLeoId] = useState("");
  const [altQuery, setAltQuery] = useState("");

  const runSearch = async (q: string) => {
    const text = q.trim();
    if (text.length < 2) return;
    setBusy(true);
    try {
      setHits(await searchTerms(text, 10));
      setDidSearch(true);
    } catch {
      setHits([]);
      setDidSearch(true);
    } finally {
      setBusy(false);
    }
  };

  const runAskLeo = async () => {
    setBusy(true);
    try {
      const seed = await searchTerms(phrase.normalized || phrase.phrase_key, 10);
      const res = await askLeoSmart(
        phrase.sample_span || phrase.normalized,
        phrase.sample_sentence || phrase.normalized,
        seed.map(toCandidate),
        phrase.extracted_tag ? [phrase.extracted_tag] : [],
      );
      setLeoReason(res.reason || "");
      setAltQuery(res.alternative_query_used || "");
      const matched = res.matched_candidate;
      if (matched?.snomed_concept_id) {
        setLeoId(matched.snomed_concept_id);
        const rest = seed.filter(
          (h) => h.snomed_concept_id !== matched.snomed_concept_id,
        );
        setHits([matched, ...rest]);
        onPick({
          concept_id: matched.snomed_concept_id,
          term: matched.term,
          semantic_tag: matched.semantic_tag,
          leo: true,
          reason: res.reason,
        });
      } else {
        setHits(seed);
      }
      setDidSearch(true);
    } catch {
      setDidSearch(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ minWidth: 0 }}>
      <div
        className="code-toolbar"
        style={{ display: "flex", gap: 8, margin: "4px 0 10px", minWidth: 0 }}
      >
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void runSearch(query);
          }}
          placeholder="Search SNOMED"
          aria-label="Search SNOMED"
          style={{
            flex: 1,
            minWidth: 0,
            height: 44,
            border: 0,
            borderRadius: 12,
            padding: "0 14px",
            background: "#F2F2F7",
            fontSize: 16,
            boxSizing: "border-box",
          }}
        />
        <button
          type="button"
          onClick={() => void runAskLeo()}
          disabled={busy}
          style={{
            flexShrink: 0,
            height: 44,
            padding: "0 14px",
            border: 0,
            borderRadius: 12,
            background: "#0F172A",
            color: "#fff",
            fontWeight: 600,
            cursor: busy ? "wait" : "pointer",
          }}
        >
          {busy ? "Asking LEO" : "Ask LEO"}
        </button>
      </div>
      {altQuery ? (
        <p style={{ fontSize: 13, color: "#9A3412", margin: "0 0 8px" }}>
          LEO searched again with &quot;{altQuery}&quot;.
        </p>
      ) : null}
      {!didSearch ? (
        <div
          data-testid="snomed-empty"
          style={{
            padding: 18,
            marginBottom: 10,
            border: "1px dashed rgba(15, 23, 42, 0.08)",
            borderRadius: 14,
            color: "#596577",
            fontSize: 14,
          }}
        >
          {hasSavedPick
            ? "Search again to change this mapping. The list stays empty until then."
            : "Search SNOMED or Ask LEO. The list stays empty until then so you do not pick the rejected guess by habit."}
        </div>
      ) : (
        <HitList
          hits={hits}
          extractedTag={phrase.extracted_tag}
          pickedId={pickedId}
          leoId={leoId}
          leoReason={leoReason}
          onPick={onPick}
        />
      )}
    </div>
  );
}

function HitList({
  hits,
  extractedTag,
  pickedId,
  leoId,
  leoReason,
  onPick,
}: {
  hits: TermSearchResult[];
  extractedTag: string;
  pickedId: string;
  leoId: string;
  leoReason: string;
  onPick: (pick: SnomedPick) => void;
}) {
  if (hits.length === 0) {
    return <p style={{ fontSize: 14, color: "#596577" }}>No SNOMED matches.</p>;
  }
  return (
    <div>
      {hits.map((hit) => {
        const leo = hit.snomed_concept_id === leoId;
        const picked = hit.snomed_concept_id === pickedId;
        const mismatch =
          extractedTag &&
          hit.semantic_tag &&
          extractedTag.toLowerCase() !== hit.semantic_tag.toLowerCase();
        return (
          <button
            key={hit.snomed_concept_id}
            type="button"
            onClick={() =>
              onPick({
                concept_id: hit.snomed_concept_id,
                term: hit.term,
                semantic_tag: hit.semantic_tag,
                leo,
                reason: leo ? leoReason : "",
              })
            }
            style={hitStyle(leo, picked)}
          >
            <strong style={{ display: "block", fontSize: 16 }}>{hit.term}</strong>
            <span style={{ display: "block", marginTop: 4, fontSize: 13, color: "#596577" }}>
              {hit.snomed_concept_id}
              {hit.semantic_tag ? ` · ${hit.semantic_tag}` : ""}
              {mismatch ? " · different tag from extraction" : ""}
            </span>
            {leo ? (
              <span
                className="leo-hot"
                style={{
                  display: "inline-flex",
                  marginTop: 8,
                  background: "#EA580C",
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 800,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  borderRadius: 999,
                  padding: "3px 10px",
                }}
              >
                LEO pick
              </span>
            ) : null}
            {leo && leoReason ? (
              <span
                style={{
                  display: "block",
                  marginTop: 8,
                  fontSize: 13,
                  color: "#9A3412",
                  fontWeight: 600,
                }}
              >
                {leoReason}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

function hitStyle(leo: boolean, picked: boolean): CSSProperties {
  if (leo) {
    return {
      display: "block",
      width: "100%",
      maxWidth: "100%",
      boxSizing: "border-box",
      textAlign: "left",
      border: picked ? "2px solid #C2410C" : "2px solid #EA580C",
      background: picked
        ? "linear-gradient(180deg, #FFEDD5 0%, #FED7AA 100%)"
        : "linear-gradient(180deg, #FFF7ED 0%, #FFEDD5 100%)",
      boxShadow: "0 0 0 1px #FDBA74, 0 10px 28px rgba(234, 88, 12, 0.38)",
      borderRadius: 14,
      padding: 14,
      marginBottom: 10,
      cursor: "pointer",
    };
  }
  return {
    display: "block",
    width: "100%",
    maxWidth: "100%",
    boxSizing: "border-box",
    textAlign: "left",
    border: picked ? "2px solid #1D4ED8" : "2px solid rgba(15, 23, 42, 0.08)",
    background: picked ? "#EFF6FF" : "#fff",
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    cursor: "pointer",
  };
}
