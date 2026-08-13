/**
 * Phrase mappings workspace chrome (DI-6BD7B681).
 *
 * Static-source verification of Inbox / drafts / review / live
 * dictionary and the empty SNOMED list until search or Ask LEO.
 */
import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "settings", "surface-forms");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Phrase mappings workspace chrome", () => {
  it("has inbox, drafts, review, and live dictionary tabs", () => {
    const src = read("page.tsx");
    expect(src).toMatch(/id: "inbox"/);
    expect(src).toMatch(/id: "drafts"/);
    expect(src).toMatch(/id: "review"/);
    expect(src).toMatch(/id: "live"/);
    expect(src).toMatch(/Live dictionary/);
  });

  it("keeps the SNOMED list empty until search or Ask LEO", () => {
    const src = read("PhraseSnomedPicker.tsx");
    expect(src).toMatch(/snomed-empty/);
    expect(src).toMatch(/Ask LEO/);
    expect(src).toMatch(/searchTerms/);
    expect(src).toMatch(/askLeoSmart/);
  });

  it("shows the saved mapping on My drafts without filling the SNOMED list", () => {
    const detail = read("PhraseDetailPane.tsx");
    const card = read("DraftMappingCard.tsx");
    const queue = read("PhraseQueueList.tsx");
    const picker = read("PhraseSnomedPicker.tsx");
    expect(card).toMatch(/data-testid="draft-mapping"/);
    expect(detail).toMatch(/DraftMappingCard/);
    expect(detail).toMatch(/draft_concept_term/);
    expect(queue).toMatch(/draft_concept_term/);
    expect(picker).toMatch(/snomed-empty/);
    expect(picker).toMatch(/hasSavedPick/);
  });

  it("looks up a missing preferred term and blocks submit until confirmed", () => {
    const card = read("DraftMappingCard.tsx");
    const page = read("page.tsx");
    const hook = read("usePhraseMappings.ts");
    expect(card).toMatch(/preferred-term-fix/);
    expect(card).toMatch(/Use this preferred term/);
    expect(card).toMatch(/searchTerms/);
    expect(page).toMatch(/term-fix-submit-hint/);
    expect(page).toMatch(/termFixCount > 0/);
    expect(hook).toMatch(/draftNeedsTermFix/);
    expect(hook).toMatch(/before submit/);
  });

  it("keeps the phrase list from covering the SNOMED search pane", () => {
    const page = read("page.tsx");
    const queue = read("PhraseQueueList.tsx");
    const detail = read("PhraseDetailPane.tsx");
    expect(page).toMatch(/data-testid="phrase-split"/);
    expect(page).toMatch(/minmax\(0,\s*38%\)/);
    expect(page).toMatch(/minmax\(0,\s*1fr\)/);
    expect(queue).toMatch(/minWidth: 0/);
    expect(detail).toMatch(/minWidth: 0/);
    expect(detail).toMatch(/overflow: "hidden"/);
  });

  it("docks save at the bottom of the detail pane", () => {
    const src = read("PhraseDetailPane.tsx");
    expect(src).toMatch(/phrase-save-dock/);
    expect(src).toMatch(/Save mapping draft/);
    expect(src).toMatch(/Exclude is harder than map/);
  });

  it("shows extraction tag and sample sentence", () => {
    const src = read("PhraseDetailPane.tsx");
    expect(src).toMatch(/Extraction tag/);
    expect(src).toMatch(/sample_sentence/);
  });

  it("publish and submit go through the two-person API", () => {
    const hook = read("usePhraseMappings.ts");
    expect(hook).toMatch(/publishPhrase/);
    expect(hook).toMatch(/submitPhraseDrafts/);
    expect(hook).toMatch(/savePhraseDraft/);
  });

  it("reads q and phrase_key from the URL", () => {
    const src = read("page.tsx");
    expect(src).toMatch(/searchParams\?\.get\("q"\)/);
    expect(src).toMatch(/searchParams\?\.get\("phrase_key"\)/);
  });
});
