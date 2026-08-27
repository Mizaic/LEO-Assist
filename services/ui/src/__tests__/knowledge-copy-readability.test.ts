/**
 * VT-LEO-AI-133 TC-001..003 - Knowledge tab copy structural and
 * readability checks.
 */

import { fleschKincaidGrade } from "@leo/design-system";

import {
  KNOWLEDGE_TAB_COPY,
  type KnowledgeTabKey,
} from "@/lib/knowledgeCopy";
import { TABS } from "@/app/admin/knowledge/page";

// The 4 roles every KNOWLEDGE_TAB_COPY entry customises copy for
// (alongside "default") -- a curated subset of the design system's
// full 28-role CANONICAL_ROLES list, not all of them (IntroRoleCopy is
// a Partial<Record<Role, ...>>, so unlisted roles just fall back to
// "default").
const CANONICAL_ROLES = [
  "triage_clinician",
  "clinician_admin",
  "regulatory_reviewer",
  "administrator",
] as const;

const EXPECTED_KEYS: KnowledgeTabKey[] = [
  "training-data",
  "surface-forms",
  "context-rules",
  "guard-rules",
  "ai-instructions",
  "clinical-guidelines",
  "pathways",
  "form-templates",
  "domains",
  "terminology",
  "results-labs",
  "validation-lab",
];

describe("VT-133 - Knowledge copy", () => {
  describe("TC-001 tab key coverage", () => {
    it("copy map keys match the TABS list exactly", () => {
      const copyKeys = Object.keys(KNOWLEDGE_TAB_COPY).sort();
      const expected = [...EXPECTED_KEYS].sort();
      expect(copyKeys).toEqual(expected);
    });

    it("TABS from knowledge/page.tsx matches the expected order", () => {
      expect(TABS.map((t) => t.key)).toEqual(EXPECTED_KEYS);
    });
  });

  describe("TC-002 role coverage", () => {
    it.each(EXPECTED_KEYS)(
      "%s has default + 4 canonical role blocks",
      (tab) => {
        const entry = KNOWLEDGE_TAB_COPY[tab];
        expect(entry).toHaveProperty("default");
        for (const role of CANONICAL_ROLES) {
          expect(entry).toHaveProperty(role);
        }
      },
    );
  });

  describe("TC-003 FK grade on default blocks", () => {
    it.each(EXPECTED_KEYS)("%s default block grades <= 9", (tab) => {
      const block = KNOWLEDGE_TAB_COPY[tab].default;
      const text = [block.title, block.lede, block.how, block.what]
        .filter(Boolean)
        .join(" ");
      const result = fleschKincaidGrade(text);
      expect(result.grade).toBeLessThanOrEqual(9);
    });
  });
});
