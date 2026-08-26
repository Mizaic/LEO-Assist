/**
 * Seed completeness rules from a detected 2WW-style letter.
 *
 * Atlas trace: DI-A0E69E38, DI-26546721, UN-3B25A20E
 */
import type { FormSchemaSection } from "./formSchemaDetector";
import type { CompletenessLogicGroup } from "./formSchemaTeach";

function leaf(name: string): CompletenessLogicGroup {
  return {
    name,
    kind: "optional",
    required: false,
    semantic_categories: [],
    concept_ids: [],
  };
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

function mandatory(name: string): CompletenessLogicGroup {
  return {
    name,
    kind: "mandatory",
    required: true,
    semantic_categories: [],
    concept_ids: [],
  };
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
  const sectionA = sections.find((section) => section.section_id === "A");
  const sites = (sectionA?.items ?? []).map((item) => item.pattern).filter(Boolean);
  if (sites.length) {
    groups.push(oneOf("Section A suspected sites", sites));
  }
  const sectionB = sections.find((section) => section.section_id === "B");
  const criteria = (sectionB?.items ?? [])
    .map((item) => item.pattern.match(/B\d+/i)?.[0] || item.pattern)
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
    groups.push(mandatory("Section D mandatory bloods"));
  }
  if (/\bBP\b|\bblood pressure\b/i.test(text)) {
    groups.push(mandatory("Blood pressure"));
  }
  if (/\bHR\b|\bheart rate\b/i.test(text)) {
    groups.push(mandatory("Heart rate"));
  }
  return groups;
}
