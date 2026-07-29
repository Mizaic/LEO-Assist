/**
 * Static verification: in-wizard back labels stay distinct from the
 * dialog footer's "Previous step" / "Next step".
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import { wizardBackLabel } from "../HighlightWizard/wizardBackLabel";

describe("wizardBackLabel", () => {
  it("names the destination instead of a bare Back", () => {
    expect(wizardBackLabel("pathway-split")).toBe("Back to always true");
    expect(wizardBackLabel("pathway-conditions", 0)).toBe("Back to situations");
    expect(wizardBackLabel("pathway-conditions", 1)).toBe("Previous situation");
    expect(wizardBackLabel("review")).toBe("Back to the last situation");
  });
});
