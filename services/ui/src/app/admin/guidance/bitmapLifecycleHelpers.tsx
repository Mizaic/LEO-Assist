/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

import { motion as fm } from "framer-motion";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import type { ReviewListItem } from "@leo/design-system";
import { celebrationPulse } from "./motionPresets";

/** Summary of resubmitting real Validation Lab patients' referrals
 * through the full pipeline, pinned to a candidate ruleset version,
 * and scoring each real run against that case's gold contract. */
export interface CandidateTestSummary {
  tested: number;
  passed: number;
  failed: number;
  errored: number;
}

export interface BitmapStatus {
  active_version: string | null;
  rule_count: number;
  compile_timestamp: string | null;
  message?: string;
  scope_type?: string;
  scope_id?: string;
  policy_mode?: string;
  compile_stats?: Record<string, number>;
}

export interface VersionEntry {
  version: string;
  active: boolean;
  scope_type?: string;
  scope_id?: string;
}

export type ScopeType = "global" | "guideline" | "domain" | "subdomain" | "custom";
export type PolicyMode = "advisory" | "strict";

export const SCOPE_OPTIONS: ReadonlyArray<{ value: ScopeType; label: string }> = [
  { value: "global", label: "Global" },
  { value: "guideline", label: "Guideline" },
  { value: "domain", label: "Domain" },
  { value: "subdomain", label: "Subdomain" },
  { value: "custom", label: "Custom" },
];

export const POLICY_OPTIONS: ReadonlyArray<{ value: PolicyMode; label: string }> = [
  { value: "advisory", label: "Advisory" },
  { value: "strict", label: "Strict" },
];

export const COMPILE_STEPS = [
  "Rules approved",
  "Compile candidate",
  "Test and go live",
];

export function buildVersionItem(
  v: VersionEntry,
  activating: string | null,
  onActivate: (ver: string) => void,
  justActivated: string | null,
  reducedMotion: boolean,
  candidateVersion: string | null,
): ReviewListItem {
  const liveChip = v.active ? <Chip label="Live" size="small" color="success" /> : null;
  const candChip =
    !v.active && v.version === candidateVersion ? (
      <Chip label="Candidate" size="small" color="info" />
    ) : null;
  const celebrateThis = v.active && v.version === justActivated;
  const chips = (
    <Stack direction="row" spacing={0.5} component="span">
      {celebrateThis ? (
        <fm.div style={{ display: "inline-flex" }} {...celebrationPulse(reducedMotion)}>
          {liveChip}
        </fm.div>
      ) : (
        liveChip
      )}
      {candChip}
    </Stack>
  );
  return {
    id: v.version,
    tone: v.active ? "positive" : "neutral",
    title: <span style={{ fontFamily: "monospace", fontSize: 13 }}>{v.version}</span>,
    chips,
    actions: v.active ? undefined : (
      <Button
        size="small"
        variant="outlined"
        disabled={activating === v.version}
        onClick={() => onActivate(v.version)}
        aria-label={`Make version ${v.version} live`}
      >
        {activating === v.version ? <CircularProgress size={14} /> : "Make this live"}
      </Button>
    ),
  };
}

export function computeActiveStep(
  activeVersion: string | null | undefined,
  candidateVersion: string | null,
  versions: VersionEntry[],
): number {
  if (activeVersion && candidateVersion && activeVersion === candidateVersion) {
    return 2;
  }
  if (candidateVersion || versions.some((v) => !v.active)) {
    return 1;
  }
  if (activeVersion) {
    return 2;
  }
  return 0;
}
