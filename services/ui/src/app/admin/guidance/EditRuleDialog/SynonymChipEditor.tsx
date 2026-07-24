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
 * Trigger badge for the synonym set + exclusions editor on a CONCEPT
 * chip (UN-LEO-AI-093 / DI-LEO-AI-511). The actual add/remove/depth
 * editor lives in `ConceptSynonymDialog.tsx`, shared with the
 * highlight-to-build wizard's own "edit an existing pick" flow, which
 * opens that dialog directly (it has no chip UI to hang this badge
 * off). This component owns only the trigger and its own open/close
 * state.
 *
 * The badge label adapts to the current state:
 *   - 0 extra seeds, 0 exclusions  -> icon-only tooltip
 *   - N>=1 extra seeds             -> "+N"
 *   - any exclusions               -> a "no-entry" icon is added
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import BlockIcon from "@mui/icons-material/Block";
import HubIcon from "@mui/icons-material/Hub";
import TuneRoundedIcon from "@mui/icons-material/TuneRounded";

import ConceptSynonymDialog, { deriveSynonymEditorState } from "./ConceptSynonymDialog";
import { friendlyTerm } from "./copy";
import type { EditableLogicNode, LogicCriterion, NodeUpdate } from "./types";

interface Props {
  node: EditableLogicNode;
  onUpdate: (u: NodeUpdate) => void;
}

export default function SynonymChipEditor({ node, onUpdate }: Props) {
  const [open, setOpen] = useState(false);
  const handleOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const criterion = node.criterion ?? ({} as LogicCriterion);
  const { seeds, excluded } = deriveSynonymEditorState(criterion);

  const extraSeedCount = Math.max(0, seeds.length - 1);
  const hasExclusions = excluded.length > 0;
  const isPopulated = extraSeedCount > 0 || hasExclusions;
  const friendlyChipLabel = friendlyTerm(criterion.preferred_term);
  const tooltip = !isPopulated
    ? `Add other codes that mean the same as "${friendlyChipLabel}", or block specific codes.`
    : `${seeds.length} code${seeds.length === 1 ? "" : "s"} on this chip${
        hasExclusions
          ? `, ${excluded.length} blocked code${excluded.length === 1 ? "" : "s"}`
          : ""
      }. Click to edit.`;
  const ariaLabel = `Edit synonyms and blocked codes for ${friendlyChipLabel}. ${
    isPopulated
      ? `${seeds.length} code${seeds.length === 1 ? "" : "s"} on this chip${
          hasExclusions ? `, ${excluded.length} blocked.` : "."
        }`
      : "No synonyms yet."
  }`;

  return (
    <>
      <Tooltip title={tooltip} arrow>
        {isPopulated ? (
          <ButtonBase
            onClick={handleOpen}
            aria-label={ariaLabel}
            sx={{
              height: 22,
              borderRadius: "11px",
              px: 0.75,
              ml: 0.5,
              gap: 0.5,
              border: "1px solid",
              borderColor: hasExclusions ? "error.light" : "info.light",
              bgcolor: hasExclusions ? "error.50" : "info.50",
              color: hasExclusions ? "error.dark" : "info.dark",
              fontSize: "0.68rem",
              fontWeight: 700,
              lineHeight: 1,
              transition:
                "background-color 120ms ease, border-color 120ms ease",
              "&:hover": {
                bgcolor: hasExclusions ? "error.100" : "info.100",
              },
              "&:focus-visible": {
                outline: "2px solid",
                outlineColor: hasExclusions ? "error.main" : "info.main",
                outlineOffset: 1,
              },
            }}
          >
            {extraSeedCount > 0 && (
              <>
                <HubIcon sx={{ fontSize: 12 }} />
                <span>+{extraSeedCount}</span>
              </>
            )}
            {hasExclusions && (
              <>
                {extraSeedCount > 0 && (
                  <Box
                    aria-hidden
                    sx={{
                      width: 1,
                      height: 10,
                      bgcolor: "currentColor",
                      opacity: 0.35,
                    }}
                  />
                )}
                <BlockIcon sx={{ fontSize: 12 }} />
                <span>{excluded.length}</span>
              </>
            )}
          </ButtonBase>
        ) : (
          <IconButton
            size="small"
            onClick={handleOpen}
            aria-label={ariaLabel}
            sx={{
              ml: 0.25,
              p: 0.25,
              color: "text.disabled",
              transition: "color 120ms ease, background-color 120ms ease",
              "&:hover": {
                color: "primary.main",
                bgcolor: "primary.50",
              },
              "&:focus-visible": {
                outline: "2px solid",
                outlineColor: "primary.main",
                outlineOffset: 1,
              },
            }}
          >
            <TuneRoundedIcon sx={{ fontSize: 14 }} />
          </IconButton>
        )}
      </Tooltip>
      <ConceptSynonymDialog
        open={open}
        node={node}
        onUpdate={onUpdate}
        onClose={handleClose}
      />
    </>
  );
}
