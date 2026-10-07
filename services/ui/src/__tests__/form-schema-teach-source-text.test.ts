/**
 * Saving a taught form sends the letter it was taught from.
 *
 * The server checks that a new form recognises its own letter, does not
 * clash with another taught form, and does not take over a letter. It can
 * only do that if the save carries the letter text (source_text). When the
 * server refuses, the reviewer sees its plain-English reason.
 *
 * Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48.
 */
import { readFileSync } from "fs";
import { join } from "path";
import { saveTaughtForm } from "../components/operations/formSchemaTeach";

const HOOK_SRC = readFileSync(
  join(__dirname, "../components/operations/useFormSchemaTeach.ts"),
  "utf8",
);
const ANNOTATOR_SRC = readFileSync(
  join(__dirname, "../components/operations/FormSchemaAnnotator.tsx"),
  "utf8",
);

const LETTER = "Section A: Cancer type suspected. Ovary [ ] Cervix [X].";

function args() {
  return {
    fingerprint: "fp-1",
    name: "Gynae 2WW",
    sections: [
      {
        section_id: "a",
        section_type: "checkbox_single" as const,
        label: "Cancer type",
        start_pattern: "Section A",
        items: [],
      },
    ],
    organizationId: "RK5",
    serviceId: "",
    completenessGroups: [],
    sourceText: LETTER,
  };
}

function mockFetch(status: number, body: unknown) {
  const fn = jest.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  global.fetch = fn as unknown as typeof fetch;
  return fn;
}

describe("saveTaughtForm sends the letter", () => {
  it("puts the letter text in the save body as source_text", async () => {
    const fetchMock = mockFetch(200, { saved: true });
    await saveTaughtForm(args());
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body).source_text).toBe(LETTER);
  });

  it("shows the server's reason when the form is refused", async () => {
    mockFetch(422, {
      detail: 'This form looks too like the taught form "Gynae". Nothing was saved.',
    });
    await expect(saveTaughtForm(args())).rejects.toThrow(
      'This form looks too like the taught form "Gynae". Nothing was saved.',
    );
  });

  it("the annotator passes its letter to the save", () => {
    const call = ANNOTATOR_SRC.match(/await saveTaughtForm\(\{([^}]*)\}\)/);
    expect(call).not.toBeNull();
    expect(call![1]).toMatch(/\bsourceText\b/);
  });

  it("the teach copy does not promise the form will never pause", () => {
    expect(ANNOTATOR_SRC).not.toMatch(/never pause/);
    expect(ANNOTATOR_SRC).toContain(
      "When you save, we check this form against the letter. Next time, we know the form by its headings.",
    );
  });

  it("the hook's save also sends the letter", () => {
    expect(HOOK_SRC).toMatch(/source_text:\s*args\.sourceText/);
  });
});
