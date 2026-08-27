/**
 * Terminology lookup tag mapping for SNOMED search filters.
 *
 * Atlas trace: DI-5C9CA57B
 */

import {
  normaliseTerminologyLookupTag,
  normaliseTerminologyLookupTags,
} from "@/lib/terminologyLookupTags";

describe("terminology lookup tag mapping", () => {
  test("observable shorthand maps to observable_entity", () => {
    expect(normaliseTerminologyLookupTag("observable")).toBe("observable_entity");
  });

  test("observation shorthand maps to observable_entity", () => {
    expect(normaliseTerminologyLookupTag("observation")).toBe("observable_entity");
  });

  test("procedure is unchanged", () => {
    expect(normaliseTerminologyLookupTag("procedure")).toBe("procedure");
  });

  test("normaliseTerminologyLookupTags dedupes mapped tags", () => {
    expect(
      normaliseTerminologyLookupTags(["observable", "observable_entity"]),
    ).toEqual(["observable_entity"]);
  });
});
