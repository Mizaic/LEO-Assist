/**
 * Choose between the Ask LEO answer and the browser's own reader.
 *
 * The browser reader is much weaker than the model, so using it must
 * always come with a notice the teacher can see.
 *
 * Atlas trace: DI-C1744ED5, DO-1C8E7598, R-98702FED
 */
import type { FormSchemaSection } from "./formSchemaDetector";
import { isIncompleteSchema } from "./formSchemaTeach";

export const BROWSER_READER_NOTICE =
  "Ask LEO could not find the sections, so we used a simpler reader in your " +
  "browser. It can miss sections. Check every section before you save.";

export type ApiDetectResult = {
  sections: FormSchemaSection[];
  notice: string;
};

export type DetectChoice = ApiDetectResult & { usedBrowserReader: boolean };

export function chooseDetection(
  api: ApiDetectResult,
  localDetect: () => FormSchemaSection[],
): DetectChoice {
  if (!isIncompleteSchema(api.sections)) {
    return { ...api, usedBrowserReader: false };
  }
  const local = localDetect();
  if (!isIncompleteSchema(local)) {
    return { sections: local, notice: BROWSER_READER_NOTICE, usedBrowserReader: true };
  }
  return {
    sections: api.sections.length ? api.sections : local,
    notice: api.notice,
    usedBrowserReader: false,
  };
}
