/**
 * Seed completeness rules from a detected 2WW-style letter.
 *
 * Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E
 *
 * Mirrors libs/pipeline/form_completeness_seed.py -- keep in sync.
 * Only universal measurements get codes. Form-specific sites and
 * criteria stay as names so a knowledge-base author can wire them.
 */
import type { FormSchemaSection } from "./formSchemaDetector";
import type { CompletenessLogicGroup } from "./formSchemaTeach";

const CONCEPT_IDS: Record<string, number[]> = {
  "blood pressure": [75367002],
  "heart rate": [364075005],
  tvus: [426491001],
  transvaginal: [426491001],
  ca125: [80529009],
  "ca 125": [80529009],
  fbc: [26604007],
  lft: [26958001],
  ue: [252167001],
  calcium: [390963002],
  ecog: [423740007],
  "clinical frailty": [763264000],
};

const SEMANTIC_TAGS: Record<string, string[]> = {
  "blood pressure": ["observable_entity"],
  "heart rate": ["observable_entity"],
  tvus: ["procedure"],
  transvaginal: ["procedure"],
  ca125: ["procedure"],
  "ca 125": ["procedure"],
  fbc: ["procedure"],
  lft: ["procedure"],
  ue: ["procedure"],
  calcium: ["procedure"],
  ecog: ["observable_entity"],
  "clinical frailty": ["observable_entity"],
};

function codesFor(name: string): { concept_ids: number[]; semantic_categories: string[] } {
  const key = name.trim().toLowerCase();
  return {
    concept_ids: CONCEPT_IDS[key] ?? [],
    semantic_categories: SEMANTIC_TAGS[key] ?? [],
  };
}

function leaf(name: string): CompletenessLogicGroup {
  return { name, kind: "optional", required: false, ...codesFor(name) };
}

function oneOf(name: string, members: string[]): CompletenessLogicGroup {
  return {
    name,
    kind: "one_of",
    required: true,
    semantic_categories: [],
    concept_ids: [],
    members: members.map(leaf),
  };
}

function nOf(
  name: string,
  members: string[],
  minCount: number,
): CompletenessLogicGroup {
  return {
    name,
    kind: "n_of",
    required: true,
    min_count: minCount,
    semantic_categories: [],
    concept_ids: [],
    members: members.map(leaf),
  };
}

function mandatory(name: string): CompletenessLogicGroup {
  return { name, kind: "mandatory", required: true, ...codesFor(name) };
}

function ifThen(ifName: string, thenName: string): CompletenessLogicGroup {
  return {
    name: `If ${ifName} then ${thenName}`,
    kind: "if_then",
    required: true,
    semantic_categories: [],
    concept_ids: [],
    if_group: leaf(ifName),
    then_group: leaf(thenName),
  };
}

export function seedCompletenessGroups(
  text: string,
  sections: FormSchemaSection[],
): CompletenessLogicGroup[] {
  const groups: CompletenessLogicGroup[] = [];

  const sectionA = sections.find((s) => s.section_id === "A");
  const sites = (sectionA?.items ?? []).map((i) => i.pattern).filter(Boolean);
  if (sites.length) {
    groups.push(oneOf("Section A suspected sites", sites));
  }

  const sectionB = sections.find((s) => s.section_id === "B");
  const criteria = (sectionB?.items ?? [])
    .map((i) => i.pattern.match(/B\d+/i)?.[0] ?? i.pattern)
    .filter(Boolean);
  if (criteria.length) {
    groups.push(oneOf("Section B referral criteria", criteria));
  }

  if (/endometr/i.test(text) && /tvus|transvaginal/i.test(text)) {
    groups.push(ifThen("Endometrium", "TVUS"));
  }
  if (/ovar/i.test(text) && /ca\s*125/i.test(text)) {
    groups.push(ifThen("Ovary", "Ca125"));
  }

  if (/mandatory|bloods done today|fbc|lft/i.test(text)) {
    groups.push(nOf("Section D mandatory bloods", ["FBC", "LFT", "UE", "Calcium"], 1));
  }
  if (/\bBP\b|\bblood pressure\b/i.test(text)) {
    groups.push(mandatory("Blood pressure"));
  }
  if (/\bHR\b|\bheart rate\b/i.test(text)) {
    groups.push(mandatory("Heart rate"));
  }
  if (/ecog|performance status|frailty/i.test(text)) {
    groups.push(oneOf("Performance status", ["ECOG", "Clinical frailty"]));
  }

  return groups;
}
