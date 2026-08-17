/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-83EBEE2C
 *   DI: DI-B954388C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-83EBEE2C")
 */
"use client";

/**
 * AI Instructions tuner -- orchestrator. State + data fetching live in
 * usePromptTuner; each tab body is an extracted `_components/` module.
 *
 * Wave E Phase 4b decomposition (DI-LEO-AI-170 / DO-LEO-AI-169 /
 * R-LEO-AI-169 / VT-LEO-AI-169). Original monolith was 1110 LOC.
 */

import type { CSSProperties } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Snackbar from "@mui/material/Snackbar";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import SaveIcon from "@mui/icons-material/Save";
import ScienceIcon from "@mui/icons-material/Science";
import { motion as fm } from "framer-motion";
import {
  PageHero,
  SegmentedTabs,
  SkeletonList,
  SpringSwap,
  StickyChrome,
  springOrInstant,
  springs,
  tapScale,
  useMotion,
} from "@leo/design-system";
import { color, typography } from "@leo/design-system/tokens";

import { IdentitySection } from "./_components/IdentitySection";
import { InstructionsTab } from "./_components/InstructionsTab";
import { OutputFormatTab } from "./_components/OutputFormatTab";
import { SandboxTab } from "./_components/SandboxTab";
import { TeachingExamplesTab } from "./_components/TeachingExamplesTab";
import {
  patchForm,
  patchSandbox,
  usePromptTuner,
  type PromptTuner,
} from "./_components/usePromptTuner";

export default function PromptTunerPage() {
  const tuner = usePromptTuner();
  if (!tuner.ui.loaded) return <PromptTunerGate tuner={tuner} mode="loading" />;
  if (tuner.ui.loadError) return <PromptTunerGate tuner={tuner} mode="error" />;
  return <PromptTunerWorkspace tuner={tuner} />;
}

function PromptTunerGate({
  tuner,
  mode,
}: {
  tuner: PromptTuner;
  mode: "loading" | "error";
}) {
  return (
    <div style={pageWrap()}>
      <BackButton onBack={tuner.goBack} />
      {mode === "loading" ? (
        <SkeletonList rows={8} />
      ) : (
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button size="small" onClick={tuner.retry}>
              Retry
            </Button>
          }
        >
          {tuner.ui.loadError}
        </Alert>
      )}
    </div>
  );
}

function PromptTunerWorkspace({ tuner }: { tuner: PromptTuner }) {
  const { form, ui, setForm, setUi } = tuner;
  return (
    <div style={pageWrap()} data-testid="prompt-tuner-workspace">
      <StickyChrome testId="prompt-tuner-chrome">
        <TunerHeader tuner={tuner} />
        <IdentitySection
          name={form.name}
          description={form.description}
          verification={form.verification}
          onNameChange={(next) => patchForm(setForm, "name", next)}
          onDescriptionChange={(next) => patchForm(setForm, "description", next)}
          onVerificationChange={(next) => patchForm(setForm, "verification", next)}
        />
        <SegmentedTabs
          tabs={tunerTabs(tuner)}
          value={ui.tab}
          onChange={(id) => setUi((u) => ({ ...u, tab: id }))}
          aria-label="Prompt configuration tabs"
        />
      </StickyChrome>
      {ui.saveError ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setUi((u) => ({ ...u, saveError: null }))}>
          {ui.saveError}
        </Alert>
      ) : null}
      <SpringSwap swapKey={ui.tab}>
        <PromptTunerTabBody tuner={tuner} />
      </SpringSwap>
      <Snackbar
        open={ui.saveSuccess}
        autoHideDuration={3000}
        onClose={() => setUi((u) => ({ ...u, saveSuccess: false }))}
        message="Saved"
      />
    </div>
  );
}

function TunerHeader({ tuner }: { tuner: PromptTuner }) {
  const { form, ui, isNew } = tuner;
  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <BackButton onBack={tuner.goBack} />
        {!isNew && form.version !== null ? (
          <span style={{ fontSize: 12, color: color.text.caption, fontFamily: typography.fontFamily.body }}>
            v{form.version}
          </span>
        ) : null}
      </div>
      <PageHero
        icon={<PsychologyOutlinedIcon />}
        title={isNew ? "New AI instructions" : form.name}
        subtitle={form.description || undefined}
        cta={{
          label: ui.saving ? "Saving..." : "Save",
          onClick: tuner.handleSave,
          icon: ui.saving ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />,
          disabled: ui.saving || !form.name,
        }}
        data-testid="prompt-tuner-hero"
      />
    </>
  );
}

function PromptTunerTabBody({ tuner }: { tuner: PromptTuner }) {
  const { form, ui, setForm } = tuner;
  if (ui.tab === "instructions") {
    return (
      <InstructionsTab
        loaded={ui.loaded}
        isNew={tuner.isNew}
        systemPrompt={form.systemPrompt}
        improving={ui.improving}
        aiSuggestion={ui.aiSuggestion}
        editorRef={tuner.editorRef}
        onEditorChange={tuner.handleEditorChange}
        onAiImprove={tuner.handleAiImprove}
        onAcceptSuggestion={tuner.handleAcceptSuggestion}
        onDismissSuggestion={() => setUiNull(tuner, "aiSuggestion")}
      />
    );
  }
  if (ui.tab === "output-format") {
    return (
      <OutputFormatTab
        outputSchema={form.outputSchema}
        onChange={(next) => patchForm(setForm, "outputSchema", next)}
      />
    );
  }
  if (ui.tab === "teaching-examples") return <TeachingBody tuner={tuner} />;
  if (ui.tab === "test-it" && !tuner.isNew) return <SandboxBody tuner={tuner} />;
  return null;
}

function TeachingBody({ tuner }: { tuner: PromptTuner }) {
  const { form, ui, setForm } = tuner;
  return (
    <TeachingExamplesTab
      examples={form.fewShotExamples}
      filteredExamples={tuner.filteredExamples}
      filterCat={ui.filterCat}
      filterScope={ui.filterScope}
      maxFewShot={tuner.maxFewShot}
      catCounts={tuner.catCounts}
      onFilterCat={(next) => tuner.setUi((u) => ({ ...u, filterCat: next }))}
      onFilterScope={(next) => tuner.setUi((u) => ({ ...u, filterScope: next }))}
      onMaxFewShot={(next) => patchForm(setForm, "maxFewShot", next)}
      onAdd={tuner.addExample}
      onUpdate={tuner.updateExample}
      onRemove={tuner.removeExample}
    />
  );
}

function SandboxBody({ tuner }: { tuner: PromptTuner }) {
  const { sandbox, setSandbox } = tuner;
  return (
    <SandboxTab
      presets={tuner.presets}
      sandboxText={sandbox.text}
      sandboxPresetId={sandbox.presetId}
      sandboxProvider={sandbox.provider}
      sandboxTier={sandbox.tier}
      sandboxDryRun={sandbox.dryRun}
      sandboxRunning={sandbox.running}
      sandboxError={sandbox.error}
      sandboxResult={sandbox.result}
      onSandboxText={(next) => patchSandbox(setSandbox, "text", next)}
      onSandboxPresetId={(next) => patchSandbox(setSandbox, "presetId", next)}
      onSandboxProvider={(next) => patchSandbox(setSandbox, "provider", next)}
      onSandboxTier={(next) => patchSandbox(setSandbox, "tier", next)}
      onSandboxDryRun={(next) => patchSandbox(setSandbox, "dryRun", next)}
      onClearError={() => patchSandbox(setSandbox, "error", null)}
      onRun={tuner.handleSandboxRun}
    />
  );
}

function setUiNull(tuner: PromptTuner, key: "aiSuggestion") {
  tuner.setUi((u) => ({ ...u, [key]: null }));
}

function tunerTabs(tuner: PromptTuner) {
  const examples = {
    id: "teaching-examples",
    label: "Teaching examples",
    count: tuner.form.fewShotExamples.length,
  };
  const testIt = {
    id: "test-it",
    label: "Test it",
    icon: <ScienceIcon sx={{ fontSize: 15 }} />,
  };
  return [
    { id: "instructions", label: "Instructions" },
    { id: "output-format", label: "Output format" },
    examples,
    ...(tuner.isNew ? [] : [testIt]),
  ];
}

function BackButton({ onBack }: { onBack: () => void }) {
  const { reducedMotion } = useMotion();
  return (
    <fm.button
      type="button"
      onClick={onBack}
      aria-label="Back"
      whileTap={tapScale(reducedMotion)}
      transition={springOrInstant(reducedMotion, springs.press)}
      style={{
        border: 0,
        background: "transparent",
        cursor: "pointer",
        padding: 6,
        color: color.text.primary,
        display: "inline-flex",
      }}
    >
      <ArrowBackIcon />
    </fm.button>
  );
}

function pageWrap(): CSSProperties {
  return {
    padding: 24,
    maxWidth: 920,
    margin: "0 auto",
    background: color.surface.canvas,
    minHeight: "100%",
  };
}
