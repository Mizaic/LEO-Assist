/**
 * Weighted checklist companions (NG12 1.7.1 7-point melanoma score).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 *
 * Score >= N with major=2 / minor=1 expands to:
 *   OR( AT_LEAST(2) majors,
 *       AND( AT_LEAST(1) major, AT_LEAST(1) minor ),
 *       AT_LEAST(3) minors )
 * when threshold is 3 and points are 2/1. Generalises for other
 * thresholds by keeping that clinically equivalent shape for the
 * NG12 instrument.
 */
import { freshNodeId } from "../treeOps";
import type { EditableLogicNode } from "../types";
import type { RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";

export interface CompanionPanelItem {
  text: string;
}

export interface CompanionPanelGroup {
  label: string;
  points: number;
  items: CompanionPanelItem[];
}

export interface CompanionPanel {
  title: string;
  kind: "weighted_checklist" | "panel" | string;
  threshold?: number;
  groups: CompanionPanelGroup[];
}

export interface WeightedChecklistState {
  title: string;
  threshold: number;
  majorPoints: number;
  minorPoints: number;
  majors: string[];
  minors: string[];
  expanded: boolean;
  lesionPhrase: string | null;
  scorePhrase: string | null;
}

const SCORE_PHRASE_RE =
  /\bweighted\s+7[\u2011\u2013\-]?point\s+checklist\s+score\s+of\s+(\d+)\s+or\s+more\b/i;
const LESION_PHRASE_RE = /\bsuspicious\s+pigmented\s+skin\s+lesion\b/i;
const SCORE_THRESHOLD_RE = /\bscore\s+of\s+(\d+)\s+or\s+more\b/i;

/** Static pack when Neo4j has not been re-ingested with companion_panels. */
export const NG12_1_7_1_COMPANION: CompanionPanel = {
  title: "Weighted 7-point checklist",
  kind: "weighted_checklist",
  threshold: 3,
  groups: [
    {
      label: "Major features of the lesions (scoring 2 points each)",
      points: 2,
      items: [
        { text: "change in size" },
        { text: "irregular shape" },
        { text: "irregular colour" },
      ],
    },
    {
      label: "Minor features of the lesions (scoring 1 point each)",
      points: 1,
      items: [
        { text: "largest diameter 7 mm or more" },
        { text: "inflammation" },
        { text: "oozing" },
        { text: "change in sensation" },
      ],
    },
  ],
};

export function parseScoreThreshold(text: string | null | undefined): number | null {
  if (!text) return null;
  const m = SCORE_THRESHOLD_RE.exec(text);
  return m ? parseInt(m[1], 10) : null;
}

export function locatePhrase(
  haystack: string,
  baseStart: number,
  phrase: string,
): RecommendationStructureItem | null {
  const idx = haystack.toLowerCase().indexOf(phrase.toLowerCase());
  if (idx < 0) return null;
  return {
    text: haystack.slice(idx, idx + phrase.length),
    start: baseStart + idx,
    end: baseStart + idx + phrase.length,
  };
}

export function peelWeightedChecklistPhrases(
  text: string,
  baseStart = 0,
): { lesion: RecommendationStructureItem | null; score: RecommendationStructureItem | null } {
  const lesionMatch = LESION_PHRASE_RE.exec(text);
  const scoreMatch = SCORE_PHRASE_RE.exec(text);
  return {
    lesion: lesionMatch
      ? {
          text: lesionMatch[0],
          start: baseStart + lesionMatch.index,
          end: baseStart + lesionMatch.index + lesionMatch[0].length,
        }
      : null,
    score: scoreMatch
      ? {
          text: scoreMatch[0],
          start: baseStart + scoreMatch.index,
          end: baseStart + scoreMatch.index + scoreMatch[0].length,
        }
      : null,
  };
}

function groupByPoints(panel: CompanionPanel): {
  majors: string[];
  minors: string[];
  majorPoints: number;
  minorPoints: number;
} {
  const sorted = [...panel.groups].sort((a, b) => b.points - a.points);
  const majorGroup = sorted[0];
  const minorGroup = sorted.find((g) => g.points < (majorGroup?.points ?? 2)) ?? sorted[1];
  return {
    majors: (majorGroup?.items ?? []).map((i) => i.text),
    minors: (minorGroup?.items ?? []).map((i) => i.text),
    majorPoints: majorGroup?.points ?? 2,
    minorPoints: minorGroup?.points ?? 1,
  };
}

export function resolveCompanionPanels(
  guidelineId: string | null | undefined,
  recommendationText: string | null | undefined,
  apiPanels: CompanionPanel[] | null | undefined,
): CompanionPanel[] {
  if (apiPanels && apiPanels.length > 0) return apiPanels;
  const text = recommendationText ?? "";
  const looksLike171 =
    /1\.7\.1\b/.test(text) ||
    (LESION_PHRASE_RE.test(text) && SCORE_PHRASE_RE.test(text));
  if (guidelineId === "NG12" && looksLike171) return [NG12_1_7_1_COMPANION];
  return [];
}

export function buildWeightedChecklistState(
  text: string,
  panels: CompanionPanel[],
  expanded = false,
): WeightedChecklistState | null {
  const panel = panels.find((p) => p.kind === "weighted_checklist") ?? panels[0];
  if (!panel || panel.groups.length === 0) return null;
  if (!SCORE_PHRASE_RE.test(text) && panel.kind !== "weighted_checklist") return null;
  const peeled = peelWeightedChecklistPhrases(text);
  if (!peeled.score && panel.kind !== "weighted_checklist") return null;
  const { majors, minors, majorPoints, minorPoints } = groupByPoints(panel);
  if (majors.length === 0 && minors.length === 0) return null;
  const threshold =
    panel.threshold ?? parseScoreThreshold(text) ?? parseScoreThreshold(peeled.score?.text) ?? 3;
  return {
    title: panel.title || "Weighted checklist",
    threshold,
    majorPoints,
    minorPoints,
    majors,
    minors,
    expanded,
    lesionPhrase: peeled.lesion?.text ?? null,
    scorePhrase: peeled.score?.text ?? null,
  };
}

/** Synthetic offsets for panel features (not in recommendation_text). */
export function featureRowsFromChecklist(
  checklist: WeightedChecklistState,
  baseStart: number,
): { lesion: RecommendationStructureItem | null; features: RecommendationStructureItem[] } {
  const peeled = checklist.lesionPhrase
    ? locatePhrase(checklist.lesionPhrase, 0, checklist.lesionPhrase)
    : null;
  // Lesion uses real offsets when we have full text; callers pass peel result.
  let cursor = baseStart + 10_000;
  const features: RecommendationStructureItem[] = [];
  for (const text of [...checklist.majors, ...checklist.minors]) {
    features.push({ text, start: cursor, end: cursor + text.length });
    cursor += text.length + 1;
  }
  return { lesion: peeled, features };
}

function blankConcept(term: string): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind: "CONCEPT",
    source_row_text: term,
    criterion: {
      snomed_concept_id: "",
      preferred_term: "",
      term,
      seeds: [],
    },
  };
}

function leafRowKey(leaf: EditableLogicNode): string {
  if (leaf.source_row_text) return leaf.source_row_text.toLowerCase();
  if (leaf.kind === "CONCEPT") {
    return (leaf.criterion?.term || leaf.criterion?.preferred_term || "").toLowerCase();
  }
  if (leaf.kind === "OBSERVATION") {
    return (leaf.observation?.observable_term || "").toLowerCase();
  }
  return "";
}

function cloneCodedOrBlank(
  source: EditableLogicNode | undefined,
  term: string,
): EditableLogicNode {
  if (!source) return blankConcept(term);

  if (
    source.kind === "OBSERVATION" &&
    source.observation?.observable_id?.trim()
  ) {
    return {
      ...source,
      node_id: freshNodeId(),
      source_row_text: term,
      observation: { ...source.observation },
    };
  }

  if (source.kind === "DEMOGRAPHIC" && source.field) {
    return {
      ...source,
      node_id: freshNodeId(),
      source_row_text: term,
    };
  }

  if (
    source.kind === "CONCEPT" &&
    (source.criterion?.snomed_concept_id || (source.criterion?.seeds?.length ?? 0) > 0)
  ) {
    return {
      ...source,
      node_id: freshNodeId(),
      source_row_text: term,
      criterion: source.criterion ? { ...source.criterion } : source.criterion,
    };
  }
  return blankConcept(term);
}

function atLeastGroup(
  role: "lead" | "trailing",
  min: number,
  children: EditableLogicNode[],
): EditableLogicNode {
  return {
    node_id: freshNodeId(),
    kind: "AT_LEAST",
    min: Math.max(1, Math.min(min, Math.max(children.length, 1))),
    cluster_role: role,
    children,
  };
}

/**
 * Rebuild pathway children as lesion AND weighted OR score tree.
 * Coded leaves matched by source_row_text / term are reused (cloned
 * into every branch that needs that feature).
 */
export function withReifiedWeightedChecklist(
  tree: EditableLogicNode,
  checklist: WeightedChecklistState,
): EditableLogicNode {
  const leaves: EditableLogicNode[] = [];
  const walk = (n: EditableLogicNode): void => {
    if (n.kind === "CONCEPT" || n.kind === "DEMOGRAPHIC" || n.kind === "OBSERVATION") {
      leaves.push(n);
      return;
    }
    for (const c of n.children ?? []) walk(c);
  };
  walk(tree);

  const byRow = new Map<string, EditableLogicNode>();
  for (const leaf of leaves) {
    const key = leafRowKey(leaf);
    if (key) byRow.set(key, leaf);
  }

  const pick = (term: string) => cloneCodedOrBlank(byRow.get(term.toLowerCase()), term);
  const majorLeaves = checklist.majors.map(pick);
  const minorLeaves = checklist.minors.map(pick);

  const twoMajors = atLeastGroup(
    "trailing",
    Math.min(2, majorLeaves.length),
    majorLeaves.map((l) => ({ ...l, node_id: freshNodeId() })),
  );
  const oneMajor = atLeastGroup(
    "lead",
    1,
    majorLeaves.map((l) => ({ ...l, node_id: freshNodeId() })),
  );
  const oneMinor = atLeastGroup(
    "trailing",
    1,
    minorLeaves.map((l) => ({ ...l, node_id: freshNodeId() })),
  );
  const threeMinors = atLeastGroup(
    "trailing",
    Math.min(3, minorLeaves.length),
    minorLeaves.map((l) => ({ ...l, node_id: freshNodeId() })),
  );

  const scoreOr: EditableLogicNode = {
    node_id: freshNodeId(),
    kind: "OR",
    children: [
      twoMajors,
      {
        node_id: freshNodeId(),
        kind: "AND",
        children: [oneMajor, oneMinor],
      },
      threeMinors,
    ],
  };

  const demographics = leaves.filter((l) => l.kind === "DEMOGRAPHIC");
  const lesionKey = (checklist.lesionPhrase || "").toLowerCase();
  const lesionLeaf =
    (lesionKey && byRow.get(lesionKey)) ||
    leaves.find(
      (l) =>
        l.kind === "CONCEPT" &&
        LESION_PHRASE_RE.test(l.source_row_text || l.criterion?.term || ""),
    );

  const children: EditableLogicNode[] = [
    ...demographics.map((d) => ({ ...d, node_id: d.node_id })),
  ];
  if (lesionLeaf && lesionLeaf.kind === "CONCEPT") {
    children.push({ ...lesionLeaf, node_id: freshNodeId() });
  } else if (checklist.lesionPhrase) {
    children.push(blankConcept(checklist.lesionPhrase));
  }
  children.push(scoreOr);

  return {
    node_id: tree.node_id,
    kind: "AND",
    children,
  };
}

export function isInstrumentRow(
  item: RecommendationStructureItem,
  checklist: WeightedChecklistState | null | undefined,
): boolean {
  if (!checklist?.scorePhrase) return false;
  return item.text.toLowerCase() === checklist.scorePhrase.toLowerCase();
}
