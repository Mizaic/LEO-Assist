/**
 * VT-CE7006EE -- selected-fact letter mentions for extraction review.
 *
 * Atlas: DI-4A012A59 / DO-E7824FED
 */
import {
  countMentions,
  focusedReviewMarks,
  mentionCopy,
} from "../components/operations/extractionReviewHighlight";

const LETTER =
  "Ovary [ ] Cervix [X] Endometrium [ ]\n" +
  "lesion on the cervix or vagina\n" +
  "Clinical examination including cervix looks normal\n" +
  "BMI: 20.2 Kg/m2";

describe("extraction review letter mentions", () => {
  test("counts each Cervix mention so the reviewer can tell them apart", () => {
    expect(countMentions(LETTER, "Cervix")).toBe(3);
  });

  test("does not count cervix inside cervical", () => {
    expect(countMentions("cervical opening and Cervix [X]", "Cervix")).toBe(1);
  });

  test("says how many times the selected fact appears", () => {
    expect(mentionCopy("Cervix", 3)).toBe("Cervix appears 3 times on the letter");
    expect(mentionCopy("polyp", 1)).toBe("polyp appears once on the letter");
    expect(mentionCopy("TSH", 0)).toBe("TSH was not found on the letter");
  });

  test("only the selected fact is marked on the letter", () => {
    const marks = focusedReviewMarks(
      [
        { text: "Cervix", semantic_tag: "body_structure", assertion: "present" },
        { text: "BMI: 20.2 Kg/m2", semantic_tag: "observable", assertion: "present" },
      ],
      "Cervix",
    );
    expect(marks).toHaveLength(1);
    expect(marks[0].term).toBe("Cervix");
    expect(marks[0].semanticTag).toBe("body_structure");
  });
});
