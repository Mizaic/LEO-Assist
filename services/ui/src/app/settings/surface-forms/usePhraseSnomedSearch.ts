/**
 * Atlas trace:
 *   DI: DI-6BD7B681
 */
"use client";

import { useId, useState } from "react";

import { askLeoSmart, searchTerms } from "@/lib/api/legacy";
import type { TermSearchResult } from "@/lib/types";

import type { UncodedPhrase } from "./phraseMappingsApi";
import type { SnomedPick } from "./PhraseSnomedPicker";

function toCandidate(row: TermSearchResult) {
  return {
    snomed_concept_id: row.snomed_concept_id,
    preferred_term: row.term,
    semantic_tag: row.semantic_tag || "",
    score: row.score ?? 0,
  };
}

async function askLeo(phrase: UncodedPhrase) {
  const seed = await searchTerms(phrase.normalized || phrase.phrase_key, 10);
  const res = await askLeoSmart(
    phrase.sample_span || phrase.normalized,
    phrase.sample_sentence || phrase.normalized,
    seed.map(toCandidate),
    phrase.extracted_tag ? [phrase.extracted_tag] : [],
  );
  return { seed, res };
}

export function usePhraseSnomedSearch(
  phrase: UncodedPhrase,
  onPick: (pick: SnomedPick) => void,
) {
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
    setBusy(true);
    try {
      const { seed, res } = await askLeo(phrase);
      setLeoReason(res.reason || "");
      setAltQuery(res.alternative_query_used || "");
      applyAskMatch({
        seed,
        matched: res.matched_candidate,
        reason: res.reason,
        setLeoId,
        setHits,
        onPick,
      });
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
  onPick: (pick: SnomedPick) => void;
}) {
  const { seed, matched, reason, setLeoId, setHits, onPick } = args;
  if (!matched?.snomed_concept_id) {
    setHits(seed);
    return;
  }
  setLeoId(matched.snomed_concept_id);
  setHits([
    matched,
    ...seed.filter((h) => h.snomed_concept_id !== matched.snomed_concept_id),
  ]);
  onPick({
    concept_id: matched.snomed_concept_id,
    term: matched.term,
    semantic_tag: matched.semantic_tag,
    leo: true,
    reason,
  });
}
