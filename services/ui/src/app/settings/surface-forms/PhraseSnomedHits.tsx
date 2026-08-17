/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { CSSProperties } from "react";

import type { TermSearchResult } from "@/lib/types";

import type { SnomedPick } from "./PhraseSnomedPicker";

export function PhraseSnomedHits({
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
      {hits.map((hit) => (
        <SnomedHitRow
          key={hit.snomed_concept_id}
          hit={hit}
          extractedTag={extractedTag}
          picked={hit.snomed_concept_id === pickedId}
          leo={hit.snomed_concept_id === leoId}
          leoReason={leoReason}
          onPick={onPick}
        />
      ))}
    </div>
  );
}

function SnomedHitRow({
  hit,
  extractedTag,
  picked,
  leo,
  leoReason,
  onPick,
}: {
  hit: TermSearchResult;
  extractedTag: string;
  picked: boolean;
  leo: boolean;
  leoReason: string;
  onPick: (pick: SnomedPick) => void;
}) {
  const mismatch =
    extractedTag &&
    hit.semantic_tag &&
    extractedTag.toLowerCase() !== hit.semantic_tag.toLowerCase();
  return (
    <button
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
      {leo ? <LeoPickBadge /> : null}
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
}

function LeoPickBadge() {
  return (
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
    border: picked ? "2px solid #0d46d6" : "2px solid rgba(15, 23, 42, 0.08)",
    background: picked ? "#EFF6FF" : "#fff",
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    cursor: "pointer",
  };
}
