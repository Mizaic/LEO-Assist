"use client";

/**
 * Step 1 -- "Who is this rule about?"
 *
 * Hosts the editable logic tree, the duplicate-set alert, the NICE
 * source toggle and the slide-in concept search drawer.
 *
 * The component is presentational: every piece of state (tree,
 * search target, coach popover, NICE toggle) lives in the parent
 * dialog so opening / closing this step preserves edits.
 *
 * Design Controls: DI-LEO-AI-234, DO-LEO-AI-234, VT-LEO-AI-510.
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Collapse from "@mui/material/Collapse";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SearchIcon from "@mui/icons-material/Search";

import ConceptSearchPanel from "../ConceptSearchPanel";
import LogicTreeEditor from "../LogicTreeEditor";
import { STEP_HELPERS, STEP_TITLES } from "../copy";
import type {
  EditableLogicNode,
  LogicCriterion,
  NodeUpdate,
} from "../types";

interface DuplicateSet {
  preview: string[];
}

interface SearchTargetView {
  mode: "replace" | "add" | "replace_action" | "idle";
  initialQuery: string;
  focusLabel: string | null;
  nodeId: string | null;
}

interface Props {
  tree: EditableLogicNode | null;
  selectedNodeId: string | null;
  duplicates: DuplicateSet[];
  recommendationText?: string;
  showRecommendation: boolean;
  onToggleRecommendation: () => void;

  searchTarget: SearchTargetView;
  searchPanelOpen: boolean;
  onOpenSearchPanel: () => void;
  onPickConcept: (criterion: LogicCriterion) => void;

  onSelectNode: (nodeId: string) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string) => void;
  onRequestCoach: (nodeId: string, anchor: HTMLElement) => void;
}

export default function Step1Who({
  tree,
  selectedNodeId,
  duplicates,
  recommendationText,
  showRecommendation,
  onToggleRecommendation,
  searchTarget,
  searchPanelOpen,
  onOpenSearchPanel,
  onPickConcept,
  onSelectNode,
  onUpdate,
  onRequestAdd,
  onRequestCoach,
}: Props) {
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <StepHeader />

      {duplicates.length > 0 && (
        <Alert
          severity="info"
          role="status"
          aria-label="Repeated symptom set warning"
          sx={{ py: 0.5 }}
        >
          {duplicates.length === 1 ? (
            <>
              This rule has the <strong>same symptom set</strong> in two
              places: {duplicates[0].preview.join(", ")}
              {duplicates[0].preview.length < 3 ? "" : ", ..."}. Keeping
              duplicates is fine, but you can remove one to keep the rule
              shorter.
            </>
          ) : (
            <>
              This rule has{" "}
              <strong>{duplicates.length} repeated symptom sets</strong>.
              Removing duplicates keeps the rule easier to read.
            </>
          )}
        </Alert>
      )}

      {recommendationText && (
        <Box>
          <Link
            component="button"
            type="button"
            variant="caption"
            onClick={onToggleRecommendation}
            sx={{ textTransform: "none" }}
          >
            {showRecommendation
              ? "Hide the original NICE text"
              : "Show the original NICE text"}
          </Link>
          {showRecommendation && (
            <Box
              sx={{
                mt: 0.5,
                p: 1.25,
                borderRadius: 1,
                bgcolor: "grey.50",
                border: "1px solid",
                borderColor: "grey.200",
              }}
            >
              <Typography
                variant="body2"
                sx={{ fontStyle: "italic", lineHeight: 1.6 }}
              >
                &ldquo;{recommendationText}&rdquo;
              </Typography>
            </Box>
          )}
        </Box>
      )}

      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={2}
        alignItems="stretch"
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {tree && (
            <LogicTreeEditor
              root={tree}
              selectedNodeId={selectedNodeId}
              onSelect={onSelectNode}
              onUpdate={onUpdate}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
            />
          )}
        </Box>
        <Box
          sx={{
            display: { xs: "block", md: "flex" },
            alignItems: "stretch",
            minWidth: 0,
          }}
        >
          <Collapse
            in={searchPanelOpen}
            orientation="horizontal"
            timeout={200}
            unmountOnExit
            sx={{
              "& .MuiCollapse-wrapperInner": {
                width: { xs: "100%", md: 380 },
              },
            }}
          >
            <Box sx={{ width: { xs: "100%", md: 380 }, pl: { md: 1.5 } }}>
              <ConceptSearchPanel
                mode={searchTarget.mode === "idle" ? "idle" : searchTarget.mode}
                focusLabel={searchTarget.focusLabel}
                initialQuery={searchTarget.initialQuery}
                onPick={onPickConcept}
              />
            </Box>
          </Collapse>
          {!searchPanelOpen && (
            <SearchPanelRail onOpen={onOpenSearchPanel} />
          )}
        </Box>
      </Stack>
    </Stack>
  );
}

function StepHeader() {
  return (
    <Box>
      <Typography
        variant="h6"
        component="h3"
        sx={{ fontWeight: 700, fontSize: "1.05rem" }}
      >
        {STEP_TITLES.who}
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ lineHeight: 1.5, mt: 0.5 }}
      >
        {STEP_HELPERS.who}
      </Typography>
    </Box>
  );
}

/**
 * Slim 56px rail shown when the search panel is collapsed. Click to
 * pin the panel open. Acts as a constant signpost so the reviewer
 * knows the search is one click away even when not in use.
 */
function SearchPanelRail({ onOpen }: { onOpen: () => void }) {
  return (
    <Tooltip title="Open search to pick a clinical term" placement="left">
      <Box
        component="button"
        type="button"
        onClick={onOpen}
        aria-label="Open search to pick a clinical term"
        sx={{
          width: { xs: "100%", md: 56 },
          minHeight: { xs: 48, md: 240 },
          ml: { md: 1 },
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 1,
          border: "1px dashed",
          borderColor: "divider",
          borderRadius: 1,
          bgcolor: "transparent",
          color: "text.secondary",
          cursor: "pointer",
          py: 1,
          "&:hover": { bgcolor: "action.hover", color: "text.primary" },
        }}
      >
        <SearchIcon fontSize="small" />
        <Typography
          variant="caption"
          sx={{
            writingMode: { md: "vertical-rl" },
            transform: { md: "rotate(180deg)" },
            letterSpacing: 0.5,
          }}
        >
          Search clinical terms
        </Typography>
      </Box>
    </Tooltip>
  );
}
