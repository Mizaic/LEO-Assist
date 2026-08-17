/**
 * SNOMED pick confirmation -- no scroll-to-save.
 *
 * Selecting a SNOMED hit opens a confirmation dialog that shows the
 * change. Confirm saves. Cancel leaves the record unchanged.
 *
 * Design Controls: DI-6BD7B681, DO-E12EC9C0, VT-76C15B0E.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

describe("SNOMED pick confirmation dialog", () => {
  const dialog = read("services/ui/src/components/SnomedPickConfirmDialog.tsx");
  const interpretations = read(
    "services/ui/src/app/admin/lab-results/InterpretationsTab.tsx",
  );
  const addObservable = read(
    "services/ui/src/app/admin/lab-results/AddObservableDialog.tsx",
  );
  const phrasePane =
    read("services/ui/src/app/settings/surface-forms/PhraseDetailPane.tsx") +
    read("services/ui/src/app/settings/surface-forms/PhraseMappingEditor.tsx");

  it("shows the picked term, code, and confirm or cancel", () => {
    expect(dialog).toMatch(/data-testid="snomed-pick-confirm"/);
    expect(dialog).toMatch(/ConfirmDialog/);
    expect(dialog).toMatch(/copy\.confirmLabel/);
    expect(dialog).toMatch(/action\.onCancel/);
    expect(dialog).toMatch(/pick\.term/);
    expect(dialog).toMatch(/pick\.conceptId/);
  });

  it("opens on interpretation pick instead of a save button below the list", () => {
    expect(interpretations).toMatch(/SnomedPickConfirmDialog/);
    expect(interpretations).toMatch(/Save this interpretation\?/);
    expect(interpretations).toMatch(/setPending/);
    expect(interpretations).not.toMatch(/id: "add-interpretation"/);
    expect(interpretations).not.toMatch(/ToolbarActions/);
  });

  it("opens on add-observable pick with name, unit, and source in the dialog", () => {
    expect(addObservable).toMatch(/SnomedPickConfirmDialog/);
    expect(addObservable).toMatch(/Add this observable\?/);
    expect(addObservable).toMatch(/Display name/);
    expect(addObservable).toMatch(/Canonical unit/);
    expect(addObservable).not.toMatch(/disabled=\{saving \|\| !pick\}/);
  });

  it("opens on phrase-mapping pick and keeps the dock for exclude", () => {
    expect(phrasePane).toMatch(/SnomedPickConfirmDialog/);
    expect(phrasePane).toMatch(/Save this mapping draft\?/);
    expect(phrasePane).toMatch(/setPending\(next\)/);
    expect(phrasePane).toMatch(/PhraseDetailSaveDock/);
    expect(phrasePane).toMatch(/onConfirmTerm: setPick/);
  });
});
