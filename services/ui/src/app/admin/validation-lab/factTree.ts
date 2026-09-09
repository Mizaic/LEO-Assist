/**
 * Group extracted facts by context, then by kind of fact.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 *
 * Atlas trace:
 *   DO: DO-7B63A6BE
 *   DI: DI-49BA8E04
 *   Risks: R-823853D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-7B63A6BE")
 */

import type { LabWorkItem } from "./inspectorTypes";
import {
  assertionKey,
  assertionLabel,
  semanticTagKey,
  semanticTagLabel,
} from "./letterMarkStyle";

export const CORE_ASSERTION_KEYS = [
  "present",
  "historical",
  "family",
  "absent",
  "planned",
] as const;

const SKIP_KINDS = new Set(["sbar", "relation"]);

export interface FactLeaf {
  text: string;
  code?: string;
  value?: string;
  unit?: string;
  relation?: string;
}

export interface FactTagGroup {
  key: string;
  label: string;
  count: number;
  leaves: FactLeaf[];
}

export interface FactTreeGroup {
  key: string;
  label: string;
  count: number;
  tags: FactTagGroup[];
}

export function buildFactTree(items: LabWorkItem[]): FactTreeGroup[] {
  const facts = items.filter((item) => !SKIP_KINDS.has(item.kind));
  const byAssertion = new Map<string, LabWorkItem[]>();
  for (const item of facts) {
    const key = assertionKey(item.assertion);
    const list = byAssertion.get(key) || [];
    list.push(item);
    byAssertion.set(key, list);
  }
  const extras = Array.from(byAssertion.keys()).filter(
    (key) => !isCoreAssertion(key),
  );
  return [...CORE_ASSERTION_KEYS, ...extras].map((key) =>
    groupFor(key, byAssertion.get(key) || []),
  );
}

export function leafFromItem(item: LabWorkItem): FactLeaf {
  const leaf: FactLeaf = { text: item.text };
  if (item.code) leaf.code = item.code;
  if (item.value) leaf.value = item.value;
  if (item.unit) leaf.unit = item.unit;
  const relation = relationLine(item);
  if (relation) leaf.relation = relation;
  return leaf;
}

function groupFor(key: string, items: LabWorkItem[]): FactTreeGroup {
  return {
    key,
    label: assertionLabel(key),
    count: items.length,
    tags: tagGroups(items),
  };
}

function tagGroups(items: LabWorkItem[]): FactTagGroup[] {
  const byTag = new Map<string, LabWorkItem[]>();
  for (const item of items) {
    const key = semanticTagKey(item.semanticTag) || "other";
    const list = byTag.get(key) || [];
    list.push(item);
    byTag.set(key, list);
  }
  return Array.from(byTag.entries()).map(([key, tagged]) => ({
    key,
    label: semanticTagLabel(key) || "Other",
    count: tagged.length,
    leaves: tagged.map(leafFromItem),
  }));
}

function relationLine(item: LabWorkItem): string {
  const parts = [item.relationType, item.relationTarget].filter(Boolean);
  return parts.join(" ");
}

function isCoreAssertion(key: string): boolean {
  return (CORE_ASSERTION_KEYS as readonly string[]).includes(key);
}
