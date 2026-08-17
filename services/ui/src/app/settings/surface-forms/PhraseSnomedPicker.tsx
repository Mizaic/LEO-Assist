/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import type { CSSProperties } from "react";
import { LeoLogo } from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

import type { UncodedPhrase } from "./phraseMappingsApi";
import { PhraseSnomedHits } from "./PhraseSnomedHits";
import { usePhraseSnomedSearch } from "./usePhraseSnomedSearch";

export interface SnomedPick {
  concept_id: string;
  term: string;
  semantic_tag?: string;
  leo?: boolean;
  reason?: string;
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
  const search = usePhraseSnomedSearch(phrase, onPick);
  return (
    <div style={{ minWidth: 0 }}>
      <SnomedSearchBar search={search} />
      {search.altQuery ? (
        <p style={{ fontSize: 13, color: color.status.warning, margin: "0 0 8px" }}>
          LEO searched again with &quot;{search.altQuery}&quot;.
        </p>
      ) : null}
      {!search.didSearch ? (
        <EmptySnomedList hasSavedPick={hasSavedPick} />
      ) : (
        <PhraseSnomedHits
          hits={search.hits}
          extractedTag={phrase.extracted_tag}
          pickedId={pickedId}
          leoId={search.leoId}
          leoReason={search.leoReason}
          onPick={onPick}
        />
      )}
    </div>
  );
}

function SnomedSearchBar({
  search,
}: {
  search: ReturnType<typeof usePhraseSnomedSearch>;
}) {
  return (
    <>
      <label
        htmlFor={search.searchId}
        style={{
          display: "block",
          margin: "4px 0 6px",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: typography.letterSpacing.caption,
          textTransform: "uppercase",
          color: color.text.secondary,
          fontFamily: typography.fontFamily.body,
        }}
      >
        Search SNOMED
      </label>
      <div
        className="code-toolbar"
        style={{ display: "flex", gap: 8, margin: "0 0 10px", minWidth: 0 }}
      >
        <input
          id={search.searchId}
          type="search"
          value={search.query}
          onChange={(e) => search.setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void search.runSearch(search.query);
          }}
          style={searchInputStyle()}
        />
        <button
          type="button"
          onClick={() => void search.runAskLeo()}
          disabled={search.busy}
          aria-busy={search.busy}
          aria-label={search.busy ? "Asking LEO" : "Ask LEO"}
          style={askLeoBtnStyle(search.busy)}
        >
          {search.busy ? (
            <LeoLogo height={16} variant="dark" spinning spinDuration={1.8} title="Asking LEO" />
          ) : (
            "Ask LEO"
          )}
        </button>
      </div>
    </>
  );
}

function searchInputStyle(): CSSProperties {
  return {
    flex: 1,
    minWidth: 0,
    height: 44,
    border: "1px solid " + color.text.secondary,
    borderRadius: 12,
    padding: "0 14px",
    background: color.surface.raised,
    color: color.text.primary,
    fontSize: 16,
    fontFamily: typography.fontFamily.body,
    boxSizing: "border-box",
  };
}

function askLeoBtnStyle(busy: boolean): CSSProperties {
  return {
    flexShrink: 0,
    height: 44,
    padding: "0 14px",
    border: 0,
    borderRadius: 12,
    background: color.text.primary,
    color: color.brand.onBrand,
    fontWeight: 600,
    fontFamily: typography.fontFamily.body,
    cursor: busy ? "wait" : "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: 88,
  };
}

function EmptySnomedList({ hasSavedPick }: { hasSavedPick: boolean }) {
  return (
    <div
      data-testid="snomed-empty"
      style={{
        padding: 18,
        marginBottom: 10,
        border: "1px dashed " + color.text.secondary,
        borderRadius: 14,
        color: color.text.secondary,
        fontSize: 14,
      }}
    >
      {hasSavedPick
        ? "Search again to change this mapping. The list stays empty until then."
        : "Search SNOMED or Ask LEO. The list stays empty until then so you do not pick the rejected guess by habit."}
    </div>
  );
}
