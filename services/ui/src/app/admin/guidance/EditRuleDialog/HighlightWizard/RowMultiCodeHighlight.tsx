/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * Step 3 row affordance: "highlight a word, assign one or more SNOMED
 * codes to it". Additive to the existing whole-row click (which still
 * resolves the row to a single concept via ConceptSearchPanel) -- this is
 * for the case where one row's text actually bundles more than one
 * clinical idea (e.g. "low haemoglobin levels, or raised platelet count")
 * and the reviewer wants to code a specific sub-phrase, possibly with more
 * than one code, rather than the row as a whole.
 *
 * Three states: collapsed (just the toggle) -> highlighting (the row's own
 * text as drag/keyboard-selectable word chunks, via
 * HighlightableRecommendationText) -> picking (MultiConceptPicker seeded
 * with the confirmed sub-phrase). Picking always adds a brand new sibling
 * CONCEPT under the pathway -- it does not attempt the AT_LEAST cluster
 * routing that whole-row clicks use (decideRowClickTarget), since a
 * highlighted sub-phrase is an explicit "add one more, independent of
 * whatever this row already resolved to" action.
 */
import { useState } from "react";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";

import HighlightableRecommendationText, {
  type TextSelectionResult,
} from "../SentenceEditor/HighlightableRecommendationText";
import type { RecommendationStructureItem } from "../SentenceEditor/pathwayTextSplit";
import MultiConceptPicker from "../MultiConceptPicker";
import type { LogicCriterion } from "../types";
import { WIZARD_TOOLTIPS } from "./copy";

type Stage = "collapsed" | "highlighting" | { picking: TextSelectionResult };

interface Props {
  item: RecommendationStructureItem;
  onAddCriterion: (criterion: LogicCriterion) => void;
}

export default function RowMultiCodeHighlight({ item, onAddCriterion }: Props) {
  const [stage, setStage] = useState<Stage>("collapsed");

  if (stage === "collapsed") {
    return (
      <Tooltip title={WIZARD_TOOLTIPS.multiCodeHighlight}>
        <Button
          size="small"
          variant="text"
          aria-label="Highlight text for more codes"
          onClick={() => setStage("highlighting")}
        >
          Highlight text for more codes
        </Button>
      </Tooltip>
    );
  }

  if (stage === "highlighting") {
    return (
      <Stack spacing={0.5} alignItems="flex-start">
        <HighlightableRecommendationText
          text={item.text}
          onConfirmSelection={(selection) => setStage({ picking: selection })}
          onCancelSelection={() => setStage("collapsed")}
        />
        <Tooltip title={WIZARD_TOOLTIPS.multiCodeClose}>
          <Button size="small" variant="text" onClick={() => setStage("collapsed")}>
            Close
          </Button>
        </Tooltip>
      </Stack>
    );
  }

  return (
    <Stack spacing={0.5}>
      <MultiConceptPicker
        initialQuery={stage.picking.text}
        embedded
        onConfirm={(criterion) => {
          onAddCriterion(criterion);
          setStage("collapsed");
        }}
      />
      <Tooltip title={WIZARD_TOOLTIPS.multiCodeClose}>
        <Button size="small" variant="text" onClick={() => setStage("collapsed")}>
          Cancel
        </Button>
      </Tooltip>
    </Stack>
  );
}
