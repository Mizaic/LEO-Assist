/**
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB, DI-6BD7B681
 */
"use client";

import type { CSSProperties } from "react";
import { motion as fm } from "framer-motion";
import { LeoLogo, tapScale, useMotion } from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

import type { TermSearchResult } from "@/lib/types";

import {
  useLabSnomedSearch,
  type LabSnomedPick,
} from "./useLabSnomedSearch";

export type { LabSnomedPick };

export function FindingSnomedPicker({
  seedText,
  hintTags,
  pickedId,
  onPick,
  label = "Search SNOMED",
}: {
  seedText: string;
  hintTags: string[];
  pickedId: string;
  onPick: (pick: LabSnomedPick) => void;
  label?: string;
}) {
  const search = useLabSnomedSearch({ seedText, hintTags, onPick });
  return (
    <div data-testid="lab-snomed-picker" style={{ minWidth: 0 }}>
      <SearchBar search={search} label={label} />
      {search.altQuery ? (
        <p style={{ fontSize: 13, color: color.status.warning, margin: "0 0 8px" }}>
          LEO searched again with &quot;{search.altQuery}&quot;.
        </p>
      ) : null}
      {!search.didSearch ? (
        <EmptySnomedList />
      ) : (
        <HitList
          hits={search.hits}
          pickedId={pickedId}
          leoId={search.leoId}
          leoReason={search.leoReason}
          onPick={onPick}
        />
      )}
    </div>
  );
}

function SearchBar({
  search,
  label,
}: {
  search: ReturnType<typeof useLabSnomedSearch>;
  label: string;
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
        {label}
      </label>
      <div style={{ display: "flex", gap: 8, margin: "0 0 10px", minWidth: 0 }}>
        <input
          id={search.searchId}
          type="search"
          value={search.query}
          onChange={(e) => search.setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void search.runSearch(search.query);
          }}
          placeholder="Search a finding, like high haemoglobin"
          style={searchInputStyle()}
        />
        <AskLeoButton busy={search.busy} onClick={() => void search.runAskLeo()} />
      </div>
    </>
  );
}

function AskLeoButton({ busy, onClick }: { busy: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      aria-busy={busy}
      aria-label={busy ? "Asking LEO" : "Ask LEO"}
      style={askLeoBtnStyle(busy)}
    >
      {busy ? (
        <LeoLogo height={16} variant="dark" spinning spinDuration={1.8} title="Asking LEO" />
      ) : (
        "Ask LEO"
      )}
    </button>
  );
}

function EmptySnomedList() {
  return (
    <div
      data-testid="lab-snomed-empty"
      style={{
        padding: 18,
        marginBottom: 10,
        border: "1px dashed " + color.text.secondary,
        borderRadius: 14,
        color: color.text.secondary,
        fontSize: 14,
      }}
    >
      Search SNOMED or Ask LEO. The list stays empty until then so you pick a real code.
    </div>
  );
}

function HitList({
  hits,
  pickedId,
  leoId,
  leoReason,
  onPick,
}: {
  hits: TermSearchResult[];
  pickedId: string;
  leoId: string;
  leoReason: string;
  onPick: (pick: LabSnomedPick) => void;
}) {
  if (hits.length === 0) {
    return <p style={{ fontSize: 14, color: color.text.secondary }}>No SNOMED matches.</p>;
  }
  return (
    <div>
      {hits.map((hit) => (
        <HitRow
          key={hit.snomed_concept_id}
          hit={hit}
          picked={hit.snomed_concept_id === pickedId}
          leo={hit.snomed_concept_id === leoId}
          leoReason={leoReason}
          onPick={onPick}
        />
      ))}
    </div>
  );
}

function HitRow({
  hit,
  picked,
  leo,
  leoReason,
  onPick,
}: {
  hit: TermSearchResult;
  picked: boolean;
  leo: boolean;
  leoReason: string;
  onPick: (pick: LabSnomedPick) => void;
}) {
  const { reducedMotion } = useMotion();
  return (
    <fm.button
      type="button"
      whileTap={tapScale(reducedMotion)}
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
      <strong style={{ display: "block", fontSize: 16, color: color.text.primary }}>
        {hit.term}
      </strong>
      <span style={{ display: "block", marginTop: 4, fontSize: 13, color: color.text.secondary }}>
        {hit.snomed_concept_id}
        {hit.semantic_tag ? ` · ${hit.semantic_tag}` : ""}
      </span>
      {leo ? <LeoPickBadge /> : null}
      {leo && leoReason ? (
        <span
          style={{
            display: "block",
            marginTop: 8,
            fontSize: 13,
            color: color.status.warning,
            fontWeight: 600,
          }}
        >
          {leoReason}
        </span>
      ) : null}
    </fm.button>
  );
}

function LeoPickBadge() {
  return (
    <span
      style={{
        display: "inline-flex",
        marginTop: 8,
        background: color.brand.secondary,
        color: color.brand.onBrand,
        fontSize: 11,
        fontWeight: 800,
        letterSpacing: typography.letterSpacing.caption,
        textTransform: "uppercase",
        borderRadius: 999,
        padding: "3px 10px",
      }}
    >
      LEO pick
    </span>
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
    minWidth: 88,
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
  };
}

function hitStyle(leo: boolean, picked: boolean): CSSProperties {
  return {
    display: "block",
    width: "100%",
    maxWidth: "100%",
    boxSizing: "border-box",
    textAlign: "left",
    border: picked
      ? "2px solid " + color.brand.primary
      : leo
        ? "2px solid " + color.brand.secondary
        : "1px solid " + color.text.secondary,
    background: picked || leo ? color.surface.alt : color.surface.raised,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    cursor: "pointer",
  };
}
