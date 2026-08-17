/**
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB, DI-6BD7B681
 */
"use client";

import { useId, useState } from "react";

import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import type { TermSearchResult } from "@/lib/types";

export interface LabSnomedPick {
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

export function useLabSnomedSearch(args: {
  seedText: string;
  hintTags: string[];
  onPick: (pick: LabSnomedPick) => void;
}) {
  const searchId = useId();
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
    } catch {
      setHits([]);
    } finally {
      setDidSearch(true);
      setBusy(false);
    }
  };

  const runAskLeo = async () => {
    const text = query.trim() || args.seedText.trim();
    if (text.length < 2) return;
    setBusy(true);
    try {
      const seed = await searchTerms(text, 10);
      const res = await askLeoSmart(text, text, seed.map(toCandidate), args.hintTags);
      setLeoReason(res.reason || "");
      setAltQuery(res.alternative_query_used || "");
      applyAskMatch({ seed, matched: res.matched_candidate, reason: res.reason, setLeoId, setHits, onPick: args.onPick });
    } catch {
      /* keep the empty list so the reviewer can search by hand */
    } finally {
      setDidSearch(true);
      setBusy(false);
    }
  };

  return {
    searchId,
    query,
    setQuery,
    hits,
    didSearch,
    busy,
    leoReason,
    leoId,
    altQuery,
    runSearch,
    runAskLeo,
  };
}

function applyAskMatch(args: {
  seed: TermSearchResult[];
  matched: TermSearchResult | null;
  reason: string | undefined;
  setLeoId: (id: string) => void;
  setHits: (hits: TermSearchResult[]) => void;
  onPick: (pick: LabSnomedPick) => void;
}) {
  if (!args.matched?.snomed_concept_id) {
    args.setHits(args.seed);
    return;
  }
  args.setLeoId(args.matched.snomed_concept_id);
  args.setHits([
    args.matched,
    ...args.seed.filter((h) => h.snomed_concept_id !== args.matched!.snomed_concept_id),
  ]);
  args.onPick({
    concept_id: args.matched.snomed_concept_id,
    term: args.matched.term,
    semantic_tag: args.matched.semantic_tag,
    leo: true,
    reason: args.reason,
  });
}
