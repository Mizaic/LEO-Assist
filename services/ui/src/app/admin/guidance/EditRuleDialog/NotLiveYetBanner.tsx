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
 * "Saved, but not live yet" banner shown on Step 4 of the rule
 * editor.
 *
 * Why this exists:
 *   Save in the editor only writes a new ``active`` rule to Neo4j and
 *   supersedes the predecessor. The runtime evaluator does not pick
 *   the change up until the next ``compile_and_store`` rebuilds the
 *   Redis bitmap and ``set_current_version`` flips the active
 *   pointer. That happens on the Bitmap Lifecycle page, which is
 *   the canonical "compile and push to live" surface.
 *
 *   Without this banner, a reviewer can quite reasonably read
 *   "Save changes" as "live for real patients", which is a clinical
 *   safety risk. The banner spells out that one more deliberate step
 *   is required before patients see the change.
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339 (see Atlas).
 */

import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Button from "@mui/material/Button";
import Tooltip from "@mui/material/Tooltip";
import OpenInNewRoundedIcon from "@mui/icons-material/OpenInNewRounded";

import { NOT_LIVE_YET_BANNER } from "./copy";

interface Props {
  /**
   * Optional href for the "Open Bitmap Lifecycle" call-to-action.
   * Falls back to the canonical knowledge-tab URL when omitted.
   */
  bitmapLifecycleHref?: string;
}

const DEFAULT_BITMAP_LIFECYCLE_HREF = "/admin/knowledge?tab=bitmap-lifecycle";

export default function NotLiveYetBanner({ bitmapLifecycleHref }: Props) {
  const href = bitmapLifecycleHref ?? DEFAULT_BITMAP_LIFECYCLE_HREF;
  return (
    <Alert
      severity="info"
      role="status"
      aria-label={NOT_LIVE_YET_BANNER.title}
      action={
        <Tooltip title="Open the page where you compile rules and make them live for patients.">
          <Button
            color="inherit"
            size="small"
            href={href}
            endIcon={<OpenInNewRoundedIcon fontSize="small" />}
            aria-label={NOT_LIVE_YET_BANNER.actionLabel}
          >
            {NOT_LIVE_YET_BANNER.actionLabel}
          </Button>
        </Tooltip>
      }
    >
      <AlertTitle sx={{ fontWeight: 700 }}>
        {NOT_LIVE_YET_BANNER.title}
      </AlertTitle>
      {NOT_LIVE_YET_BANNER.body}
    </Alert>
  );
}
