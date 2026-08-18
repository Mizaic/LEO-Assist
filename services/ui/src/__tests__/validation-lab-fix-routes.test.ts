/**
 * VT-5E51F5D9 -- Fix routing URLs for Validation Lab findings.
 *
 * Atlas: DI-562F2C9E / DO-4FD76836
 */

import { fixHref, isInlineFix } from "../app/admin/validation-lab/fixRoutes";

describe("fixHref", () => {
  test("routes extraction to AI instructions", () => {
    expect(fixHref({ category: "extraction", promptName: "extraction_v1" })).toBe(
      "/admin/knowledge?tab=ai-instructions&prompt_name=extraction_v1",
    );
  });

  test("routes context to context-rules with term", () => {
    expect(fixHref({ category: "context", target: "family history" })).toContain(
      "tab=context-rules",
    );
    expect(fixHref({ category: "context", target: "family history" })).toContain(
      "term=family",
    );
  });

  test("routes guard to pipeline guards", () => {
    const href = fixHref({
      category: "guard",
      firedRuleId: "scope-1",
      sourceSentence: "no chest pain",
    });
    expect(href).toContain("tab=guard-rules");
    expect(href).toContain("fired_rule_id=scope-1");
  });

  test("routes phrase mapping to surface-forms", () => {
    const href = fixHref({ category: "phrase_mapping", target: "SOB" });
    expect(href).toContain("tab=surface-forms");
    expect(href).toContain("phrase_key=SOB");
  });

  test("routes guideline_rule to clinical guidelines", () => {
    const href = fixHref({
      category: "guideline_rule",
      guidelineRuleId: "rule:NG12:1",
    });
    expect(href).toContain("tab=clinical-guidelines");
    expect(href).toContain("rule_id=rule");
  });

  test("routes semantic_tag to AI instructions", () => {
    const href = fixHref({
      category: "semantic_tag",
      target: "standard proton pump inhibitor therapy",
    });
    expect(href).toContain("tab=ai-instructions");
    expect(href).toContain("prompt_name=");
  });

  test("inline fix is phrase mapping or guard", () => {
    expect(isInlineFix("phrase_mapping")).toBe(true);
    expect(isInlineFix("guard")).toBe(true);
    expect(isInlineFix("extraction")).toBe(false);
    expect(isInlineFix("semantic_tag")).toBe(false);
  });
});
