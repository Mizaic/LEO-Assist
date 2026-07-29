/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-15565AF5
 *   DI: DI-3DDA3519
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-15565AF5")
 */
"use client";

import { motion as fm } from "framer-motion";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
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
  rule_count?: number;
  compile_timestamp?: string | null;
  policy_mode?: string | null;
  compile_stats?: Record<string, number>;
}

/** Short local stamp for compile_timestamp ISO strings. */
export function formatCompileTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** One-line meta under a compiled version id. */
export function formatVersionMeta(v: VersionEntry): string {
  const parts: string[] = [];
  const when = formatCompileTime(v.compile_timestamp);
  if (when) parts.push(when);
  if (typeof v.rule_count === "number") {
    parts.push(`${v.rule_count} rule${v.rule_count === 1 ? "" : "s"}`);
  }
  if (v.policy_mode) parts.push(v.policy_mode);
  const stats = v.compile_stats || {};
  const included = stats.rules_included;
  const excluded = stats.rules_excluded;
  const violations = stats.policy_violations;
  if (
    typeof included === "number" ||
    typeof excluded === "number" ||
    typeof violations === "number"
  ) {
    parts.push(
      `included ${included ?? 0} · excluded ${excluded ?? 0} · violations ${violations ?? 0}`,
    );
  }
  return parts.join(" · ");
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
  const metaText = formatVersionMeta(v);
  return {
    id: v.version,
    tone: v.active ? "positive" : "neutral",
    title: <span style={{ fontFamily: "monospace", fontSize: 13 }}>{v.version}</span>,
    meta: metaText ? (
      <span data-testid={`bitmap-version-meta-${v.version}`}>{metaText}</span>
    ) : undefined,
    chips,
    actions: v.active ? undefined : (
      <Tooltip title="Make this compiled version the one used for real patients.">
        <span>
          <Button
            size="small"
            variant="outlined"
            disabled={activating === v.version}
            onClick={() => onActivate(v.version)}
            aria-label={`Make version ${v.version} live`}
          >
            {activating === v.version ? <CircularProgress size={14} /> : "Make this live"}
          </Button>
        </span>
      </Tooltip>
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
