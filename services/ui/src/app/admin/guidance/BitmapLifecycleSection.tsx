/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-599B9828
 *   DI: DI-8DD23CE2
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-599B9828")
 */
"use client";

import Link from "next/link";
import { AnimatePresence, motion as fm } from "framer-motion";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import MuiStep from "@mui/material/Step";
import MuiStepLabel from "@mui/material/StepLabel";
import MuiStepper from "@mui/material/Stepper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CelebrationRoundedIcon from "@mui/icons-material/CelebrationRounded";
import ConfirmDialog from "@/components/ConfirmDialog";
import {
  FilterBar,
  ProgressiveReveal,
  ProgressStrip,
  ReviewListCard,
  StatHero,
  ToolbarActions,
  useMotion,
  type FilterChip,
  type StatTile,
} from "@leo/design-system";
import { celebrationPulse, popVariants } from "./motionPresets";
import {
  COMPILE_STEPS,
  POLICY_OPTIONS,
  SCOPE_OPTIONS,
  buildVersionItem,
  compilePhaseLabel,
  computeActiveStep,
  formatCompileElapsed,
} from "./bitmapLifecycleHelpers";
import CandidateLabTestDialog from "./CandidateLabTestDialog";
import { useBitmapLifecycle } from "./useBitmapLifecycle";

interface BitmapLifecycleSectionProps {
  onVersionActivated?: () => void;
}

export default function BitmapLifecycleSection({
  onVersionActivated,
}: BitmapLifecycleSectionProps) {
  const { reducedMotion } = useMotion();
  const life = useBitmapLifecycle({ onVersionActivated });
  const activeStep = computeActiveStep(
    life.status?.active_version,
    life.candidateVersion,
    life.versions,
  );
  const scopeChips: FilterChip[] = SCOPE_OPTIONS.map((o) => ({
    id: o.value,
    label: o.label,
    active: life.scopeType === o.value,
    onToggle: () => life.setScopeType(o.value),
  }));
  const compileStats = life.status?.compile_stats;
  const statTiles: StatTile[] = compileStats
    ? [
        {
          id: "included",
          label: "In bitmap",
          value: compileStats.rules_included ?? 0,
        },
        {
          id: "excluded",
          label: "Dropped at compile",
          value: compileStats.rules_excluded ?? 0,
        },
        {
          id: "violations",
          label: "Policy issues",
          value: compileStats.policy_violations ?? 0,
        },
      ]
    : [];

  return (
    <Box>
      <MuiStepper activeStep={activeStep} sx={{ mb: 2 }}>
        {COMPILE_STEPS.map((label) => (
          <MuiStep key={label}>
            <MuiStepLabel>{label}</MuiStepLabel>
          </MuiStep>
        ))}
      </MuiStepper>
      <ProgressStrip
        label={`Step ${activeStep + 1} of ${COMPILE_STEPS.length}`}
        value={activeStep}
        total={COMPILE_STEPS.length - 1}
        subtitle={`${activeStep + 1} of ${COMPILE_STEPS.length} steps complete`}
        tone={activeStep === COMPILE_STEPS.length - 1 ? "positive" : "neutral"}
      />
      {life.error && (
        <Alert severity="error" sx={{ mb: 2, mt: 2 }}>
          {life.error}
        </Alert>
      )}
      <Box sx={{ mt: 2, mb: 1.5 }}>
        <FilterBar
          search={life.scopeType === "global" ? "" : life.scopeId}
          onSearchChange={(v) => {
            if (life.scopeType !== "global") life.setScopeId(v);
          }}
          searchPlaceholder={
            life.scopeType === "subdomain"
              ? "cancer_audit:symptoms"
              : "NG12 or cancer_audit"
          }
          aria-label="Scope filter"
          chips={scopeChips}
        />
      </Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
        <Typography variant="body2" color="text.secondary">
          Policy:
        </Typography>
        <ToolbarActions
          align="start"
          actions={POLICY_OPTIONS.map((o) => ({
            id: o.value,
            label: o.label,
            variant: life.policyMode === o.value ? "primary" : "secondary",
            onClick: () => life.setPolicyMode(o.value),
          }))}
        />
      </Stack>
      <Box sx={{ mb: 2 }}>
        <ProgressiveReveal summary="Advanced options">
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 1 }}>
            <TextField
              size="small"
              label="Child depth override"
              value={life.distanceChild}
              onChange={(e) => life.setDistanceChild(e.target.value)}
              sx={{ width: 190 }}
              helperText="Optional. Leave empty to use rule default."
            />
            <TextField
              size="small"
              label="Parent depth override"
              value={life.distanceParent}
              onChange={(e) => life.setDistanceParent(e.target.value)}
              sx={{ width: 190 }}
              helperText="Optional. Leave empty to use rule default."
            />
          </Stack>
        </ProgressiveReveal>
      </Box>
      {life.status && (
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Active version:
          </Typography>
          {life.status.active_version ? (
            <fm.div
              style={{ display: "inline-flex" }}
              {...(life.status.active_version === life.justActivatedVersion
                ? celebrationPulse(reducedMotion)
                : {})}
            >
              <Chip label={life.status.active_version} color="success" size="small" />
            </fm.div>
          ) : (
            <Chip label="No active version" size="small" />
          )}
          {life.status.rule_count > 0 && (
            <Typography variant="body2" color="text.secondary">
              {life.status.rule_count} rule{life.status.rule_count !== 1 ? "s" : ""} live
            </Typography>
          )}
        </Stack>
      )}
      {life.status?.message && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {life.status.message}
        </Typography>
      )}
      {statTiles.length > 0 && <StatHero stats={statTiles} />}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap">
        <ToolbarActions
          actions={[
            {
              id: "compile",
              label: life.compiling ? "Compiling..." : "Compile candidate",
              variant: "primary",
              onClick: life.handleCompile,
              disabled: life.compiling,
              loading: life.compiling,
              title: "Build a new candidate ruleset from approved rules. It is not live yet.",
            },
            {
              id: "test-lab-patients",
              label: life.labTestOpen ? "Testing..." : "Test with Lab patients",
              variant: "secondary",
              onClick: life.handleTestOnLabPatients,
              disabled:
                !life.versions.length || life.labTestOpen || life.compiling,
              loading: life.labTestOpen,
              title:
                "Pick a compiled bitmap and run real Lab patients against it. Live care stays on the current version.",
            },
            {
              id: "historic-shadow",
              label: life.shadowing ? "Comparing..." : "Historic shadow",
              variant: "secondary",
              onClick: life.handleHistoricShadow,
              disabled: !life.candidateVersion || life.shadowing || life.compiling,
              loading: life.shadowing,
              title: "Compare the candidate against historic cases without changing live care.",
            },
            {
              id: "rollback",
              label: life.rollingBack ? "Rolling back..." : "Rollback scope",
              variant: "secondary",
              onClick: life.handleRollback,
              disabled: life.rollingBack || life.versions.length < 2,
              loading: life.rollingBack,
              title: "Undo the last live change for this scope.",
            },
          ]}
        />
        <AnimatePresence>
          {life.justCompiled && (
            <fm.div
              variants={popVariants(reducedMotion)}
              initial="initial"
              animate="animate"
              exit="exit"
            >
              <Chip
                icon={<CelebrationRoundedIcon fontSize="small" />}
                label="Compiled!"
                size="small"
                color="success"
              />
            </fm.div>
          )}
        </AnimatePresence>
      </Stack>
      {life.candidateVersion && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Candidate:{" "}
          <span style={{ fontFamily: "monospace" }}>{life.candidateVersion}</span>
          {" -- "}not live until you choose Make this live.
        </Typography>
      )}
      {life.shadowSummary && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {life.shadowSummary}
        </Alert>
      )}
      {life.compiling && (
        <Box sx={{ mb: 2 }} data-testid="bitmap-compile-progress">
          <AnimatePresence mode="wait">
            <fm.div
              key={compilePhaseLabel(life.compileElapsedSec)}
              initial={reducedMotion ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={reducedMotion ? undefined : { opacity: 0, y: -4 }}
              transition={{ duration: reducedMotion ? 0 : 0.22 }}
            >
              <ProgressStrip
                indeterminate
                label={compilePhaseLabel(life.compileElapsedSec)}
                subtitle={`Elapsed ${formatCompileElapsed(life.compileElapsedSec)}`}
              />
            </fm.div>
          </AnimatePresence>
        </Box>
      )}
      {life.candidateTestSummary && (
        <Box
          sx={{
            mb: 2,
            p: 1.5,
            borderRadius: 1,
            bgcolor: life.candidateTestSummary.failed > 0 ? "error.50" : "success.50",
            border: "1px solid",
            borderColor:
              life.candidateTestSummary.failed > 0 ? "error.200" : "success.200",
          }}
        >
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="body2">
              Lab patient test (bitmap{" "}
              <span style={{ fontFamily: "monospace" }}>
                {life.candidateTestSummary.rulesetVersion ||
                  life.candidateVersion ||
                  "n/a"}
              </span>
              ):
            </Typography>
            <Chip
              size="small"
              color={life.candidateTestSummary.failed === 0 ? "success" : "error"}
              label={`${life.candidateTestSummary.failed} failed`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`${life.candidateTestSummary.passed} passed`}
            />
            <Chip
              size="small"
              variant="outlined"
              label={`${life.candidateTestSummary.tested} patients`}
            />
            {life.candidateTestSummary.errored > 0 && (
              <Chip
                size="small"
                color="warning"
                label={`${life.candidateTestSummary.errored} could not run`}
              />
            )}
            <Box sx={{ flex: 1 }} />
            <Button
              component={Link}
              href="/admin/validation-lab"
              size="small"
              variant="text"
            >
              Open Validation Lab
            </Button>
          </Stack>
          {life.candidateTestSummary.failed > 0 && (
            <Typography variant="caption" color="error">
              The candidate produced a different result against gold for at least
              one patient. Do not go live until you have reviewed it.
            </Typography>
          )}
        </Box>
      )}
      {life.versions.length > 0 && (
        <Box>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 1 }}
          >
            All compiled versions
          </Typography>
          <ReviewListCard
            items={life.versions.map((v) =>
              buildVersionItem(
                v,
                life.activatingVersion,
                life.setConfirmVersion,
                life.justActivatedVersion,
                reducedMotion,
                life.candidateVersion,
              ),
            )}
          />
        </Box>
      )}
      {life.confirmVersion && (
        <ConfirmDialog
          title="Make this version live?"
          body={`This will update how the system matches patients to guidelines. Version ${life.confirmVersion} will become active straight away.`}
          confirmLabel="Yes, go live"
          cancelLabel="Cancel"
          variant="danger"
          busy={life.activatingVersion === life.confirmVersion}
          busyLabel="Going live..."
          onConfirm={() => life.handleActivate(life.confirmVersion!)}
          onCancel={() => {
            if (life.activatingVersion) return;
            life.setConfirmVersion(null);
          }}
        />
      )}
      <CandidateLabTestDialog
        open={life.labTestOpen}
        versions={life.versions}
        preferredVersion={life.candidateVersion}
        onClose={life.handleLabTestClose}
        onComplete={life.handleLabTestComplete}
      />
    </Box>
  );
}
