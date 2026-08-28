/**
 * Seed completeness rules from a detected 2WW-style letter.
 *
 * Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E
 *
 * Mirrors libs/pipeline/form_completeness_seed.py -- keep in sync.
 * All SNOMED IDs verified active in the UK release (ecca11a1 knowledge graph).
 */
import type { FormSchemaSection } from "./formSchemaDetector";
import type { CompletenessLogicGroup } from "./formSchemaTeach";

const CONCEPT_IDS: Record<string, number[]> = {
  // Minimum Dataset vitals
  "blood pressure": [75367002],
  "heart rate": [364075005],
  // Procedures required by 2WW rules
  tvus: [426491001],
  transvaginal: [426491001],
  ca125: [80529009],
  "ca 125": [80529009],
  // Section A cancer sites -- IS_A expansion covers descendants
  cervix: [363354003, 315266007],
  endometrium: [254878006, 93781006, 123844007],
  ovary: [363443007, 762997004, 93934004],
  vagina: [363445000, 372025005],
  vulva: [363367000, 762996008, 94143002],
  // Section B criteria
  b1: [363354003, 315266007],
  b3: [163367002],
  b4: [163367002],
  b5: [76742009],
  b6: [48880000],
  b9: [363443007, 80529009],
  // Section D mandatory bloods
  fbc: [26604007],
  lft: [26958001],
  ue: [252167001],
  calcium: [390963002],
  // Performance status
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
  // Cancer sites and B-criteria: match by concept ID only
  cervix: [],
  endometrium: [],
  ovary: [],
  vagina: [],
  vulva: [],
  fbc: ["procedure"],
  lft: ["procedure"],
  ue: ["procedure"],
  calcium: ["procedure"],
  ecog: ["observable_entity"],
  "clinical frailty": ["observable_entity"],
};

// Section B label -> lookup key
const SECTION_B_KEY: Record<string, string> = {
  b1: "b1",
  b2: "vulva",
  b3: "b3",
  b4: "b4",
  b5: "b5",
  b6: "b6",
  b9: "b9",
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

function sectionBLeaf(label: string): CompletenessLogicGroup {
  const key = SECTION_B_KEY[label.trim().toLowerCase()] ?? label.toLowerCase();
  const { concept_ids, semantic_categories } = codesFor(key);
  return { name: label, kind: "optional", required: false, concept_ids, semantic_categories };
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

  // Section A: suspected cancer site
  const sectionA = sections.find((s) => s.section_id === "A");
  const sites = (sectionA?.items ?? []).map((i) => i.pattern).filter(Boolean);
  if (sites.length) {
    groups.push(oneOf("Section A suspected sites", sites));
  }

  // Section B: at least one 14-day-rule criterion
  const sectionB = sections.find((s) => s.section_id === "B");
  const criteria = (sectionB?.items ?? [])
    .map((i) => i.pattern.match(/B\d+/i)?.[0] ?? i.pattern)
    .filter(Boolean);
  if (criteria.length) {
    const members = criteria.map(sectionBLeaf);
    groups.push({
      name: "Section B referral criteria",
      kind: "one_of",
      required: true,
      semantic_categories: [],
      concept_ids: [],
      members,
    });
  }

  // If-then rules from the form's own instructions
  if (/endometr/i.test(text) && /tvus|transvaginal/i.test(text)) {
    groups.push(ifThen("Endometrium", "TVUS"));
  }
  if (/ovar/i.test(text) && /ca\s*125/i.test(text)) {
    groups.push(ifThen("Ovary", "Ca125"));
  }

  // Section D mandatory bloods (at least one result present)
  if (/mandatory|bloods done today|fbc|lft/i.test(text)) {
    groups.push(nOf("Section D mandatory bloods", ["FBC", "LFT", "UE", "Calcium"], 1));
  }

  // Minimum Dataset vitals
  if (/\bBP\b|\bblood pressure\b/i.test(text)) {
    groups.push(mandatory("Blood pressure"));
  }
  if (/\bHR\b|\bheart rate\b/i.test(text)) {
    groups.push(mandatory("Heart rate"));
  }

  // Performance status
  if (/ecog|performance status|frailty/i.test(text)) {
    groups.push({
      name: "Performance status",
      kind: "one_of",
      required: true,
      semantic_categories: [],
      concept_ids: [],
      members: [leaf("ECOG"), leaf("Clinical frailty")],
    });
  }

  return groups;
}
