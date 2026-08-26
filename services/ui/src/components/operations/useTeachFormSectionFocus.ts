/**
 * Shared focus state for Teach this form letter and annotator panes.
 *
 * Atlas trace: DI-5C9CA57B, DO-D0C19842
 */
import { useCallback, useState } from "react";

import type { FormSchemaSection } from "./formSchemaDetector";
import { matchSectionFromLetterText } from "./formSchemaSectionFocus";

export function useTeachFormSectionFocus() {
  const [focusedSectionId, setFocusedSectionId] = useState<string | null>(null);
  const [highlightedRegionId, setHighlightedRegionId] = useState<string | null>(
    null,
  );

  const selectSection = useCallback((section: FormSchemaSection) => {
    setFocusedSectionId(section.section_id);
    setHighlightedRegionId(section.section_id);
  }, []);

  const selectLetterText = useCallback(
    (sections: FormSchemaSection[], text: string) => {
      const match = matchSectionFromLetterText(sections, text);
      if (!match) return;
      setFocusedSectionId(match.section_id);
      setHighlightedRegionId(match.section_id);
    },
    [],
  );

  return {
    focusedSectionId,
    highlightedRegionId,
    selectSection,
    selectLetterText,
  };
}
