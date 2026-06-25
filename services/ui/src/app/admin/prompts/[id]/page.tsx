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
 * AI Instructions tuner -- orchestrator. State + data fetching live here;
 * each tab body is rendered by an extracted component in `_components/`.
 *
 * Wave E Phase 4b decomposition (DI-LEO-AI-170 / DO-LEO-AI-169 /
 * R-LEO-AI-169 / VT-LEO-AI-169). Original monolith was 1110 LOC.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import SaveIcon from "@mui/icons-material/Save";
import ScienceIcon from "@mui/icons-material/Science";

import { PageHero, SegmentedTabs, SkeletonList } from "@leo/design-system";

import type { MarkdownEditorHandle } from "@/components/markdown-editor";
import { api } from "@/lib/api";

import { IdentitySection } from "./_components/IdentitySection";
import { InstructionsTab } from "./_components/InstructionsTab";
import { OutputFormatTab } from "./_components/OutputFormatTab";
import { SandboxTab } from "./_components/SandboxTab";
import { TeachingExamplesTab } from "./_components/TeachingExamplesTab";
import {
  DEFAULT_MAX_FEW_SHOT,
  type FewShotExample,
  type PresetItem,
  type PromptConfigData,
  type SandboxProvider,
  type SandboxResult,
  type SandboxTier,
} from "./_components/types";

export default function PromptTunerPage() {
  const params = useParams();
  const router = useRouter();
  const promptId = params.id as string;
  const isNew = promptId === "new";

  const editorRef = useRef<MarkdownEditorHandle>(null);

  const [tab, setTab] = useState<string>("instructions");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [outputSchema, setOutputSchema] = useState("{}");
  const [verification, setVerification] = useState(false);
  const [fewShotExamples, setFewShotExamples] = useState<FewShotExample[]>([]);
  const [maxFewShot, setMaxFewShot] = useState(DEFAULT_MAX_FEW_SHOT);
  const [aiSuggestion, setAiSuggestion] = useState<string | null>(null);
  const [improving, setImproving] = useState(false);
  const [saving, setSaving] = useState(false);
  const [version, setVersion] = useState<number | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const [filterCat, setFilterCat] = useState("");
  const [filterScope, setFilterScope] = useState("");

  const [sandboxText, setSandboxText] = useState("");
  const [sandboxPresetId, setSandboxPresetId] = useState<string>("__custom__");
  const [sandboxProvider, setSandboxProvider] = useState<SandboxProvider>("aws");
  const [sandboxTier, setSandboxTier] = useState<SandboxTier>("small");
  const [sandboxDryRun, setSandboxDryRun] = useState(true);
  const [sandboxRunning, setSandboxRunning] = useState(false);
  const [sandboxError, setSandboxError] = useState<string | null>(null);
  const [sandboxResult, setSandboxResult] = useState<SandboxResult | null>(null);
  const [presets, setPresets] = useState<PresetItem[]>([]);

  useEffect(() => {
    api
      .get<{ presets: PresetItem[] }>("/api/presets")
      .then((data) => setPresets(data.presets || []))
      .catch(() => {
        /* presets unavailable -- fall back to custom */
      });
  }, []);

  useEffect(() => {
    if (isNew) {
      setLoaded(true);
      return;
    }
    setLoaded(false);
    setLoadError(null);
    api
      .get<PromptConfigData>(`/api/prompts/${promptId}`)
      .then((data) => {
        setName(data.name);
        setDescription(data.description || "");
        setSystemPrompt(data.systemPrompt);
        setOutputSchema(data.outputSchema || "{}");
        setVerification(data.verification);
        setFewShotExamples(
          (data.fewShotExamples || []).map((ex) => ({
            ...ex,
            category: ex.category ?? "",
            model_scope: ex.model_scope ?? "any",
            description: ex.description ?? "",
            core: Boolean(ex.core),
          })),
        );
        setMaxFewShot(data.maxFewShot ?? DEFAULT_MAX_FEW_SHOT);
        setVersion(data.version);
        setLoaded(true);
      })
      .catch(() => {
        setLoadError("Failed to load. Please try again.");
        setLoaded(true);
      });
  }, [promptId, isNew, retryKey]);

  const handleEditorChange = useCallback(
    (md: string) => setSystemPrompt(md),
    [],
  );

  const handleAiImprove = useCallback(async () => {
    setImproving(true);
    try {
      const result = await api.post<{ improvedPrompt: string }>(
        "/api/prompts/improve",
        { currentPrompt: systemPrompt, outputSchema },
      );
      setAiSuggestion(result.improvedPrompt);
    } catch {
      setAiSuggestion(null);
    } finally {
      setImproving(false);
    }
  }, [systemPrompt, outputSchema]);

  const handleAcceptSuggestion = useCallback((suggestion: string) => {
    editorRef.current?.setMarkdown(suggestion);
    setSystemPrompt(suggestion);
    setAiSuggestion(null);
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    const payload = {
      name,
      description,
      systemPrompt: editorRef.current?.getMarkdown() ?? systemPrompt,
      outputSchema,
      verification,
      fewShotExamples,
      maxFewShot,
    };
    try {
      if (isNew) {
        const result = await api.post<{ id: string }>("/api/prompts", payload);
        router.push(`/admin/prompts/${result.id}`);
      } else {
        await api.put(`/api/prompts/${promptId}`, payload);
        setSaveSuccess(true);
      }
    } catch {
      setSaveError("Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  }, [
    name,
    description,
    systemPrompt,
    outputSchema,
    verification,
    fewShotExamples,
    maxFewShot,
    isNew,
    promptId,
    router,
  ]);

  const addExample = useCallback(() => {
    setFewShotExamples((prev) => [
      ...prev,
      {
        id: `ex_${Date.now()}`,
        input: "",
        output: "",
        deidentified: false,
        category: "",
        model_scope: "any",
        description: "",
        core: false,
      },
    ]);
  }, []);

  const removeExample = useCallback((id: string) => {
    setFewShotExamples((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const updateExample = useCallback(
    (id: string, field: keyof FewShotExample, value: string | boolean) => {
      setFewShotExamples((prev) =>
        prev.map((e) => (e.id === id ? { ...e, [field]: value } : e)),
      );
    },
    [],
  );

  const handleSandboxRun = useCallback(async () => {
    if (!sandboxText.trim() || isNew) return;
    setSandboxRunning(true);
    setSandboxError(null);
    setSandboxResult(null);
    try {
      const payload: Record<string, unknown> = {
        encounterText: sandboxText,
        dryRun: sandboxDryRun,
      };
      if (sandboxPresetId && sandboxPresetId !== "__custom__") {
        payload.presetId = sandboxPresetId;
      } else {
        payload.provider = sandboxProvider;
        payload.tier = sandboxTier;
      }
      const result = await api.post(
        `/api/prompts/${promptId}/simulate`,
        payload,
      );
      setSandboxResult(result as SandboxResult);
    } catch (err: unknown) {
      setSandboxError(
        err instanceof Error ? err.message : "Simulation failed",
      );
    } finally {
      setSandboxRunning(false);
    }
  }, [
    sandboxText,
    sandboxPresetId,
    sandboxProvider,
    sandboxTier,
    sandboxDryRun,
    promptId,
    isNew,
  ]);

  const filteredExamples = fewShotExamples.filter((ex) => {
    if (filterCat && ex.category !== filterCat) return false;
    if (filterScope && ex.model_scope !== filterScope) return false;
    return true;
  });

  const catCounts = fewShotExamples.reduce<Record<string, number>>(
    (acc, ex) => {
      const k = ex.category || "uncategorised";
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    },
    {},
  );
  const coreCount = fewShotExamples.filter((ex) => ex.core).length;

  if (!loaded) {
    return (
      <Box sx={{ p: 3, maxWidth: 920, mx: "auto" }}>
        <IconButton
          onClick={() => router.push("/admin/knowledge?tab=ai-instructions")}
          aria-label="Back"
          sx={{ mb: 1 }}
        >
          <ArrowBackIcon />
        </IconButton>
        <SkeletonList rows={8} />
      </Box>
    );
  }

  if (loadError) {
    return (
      <Box sx={{ p: 3, maxWidth: 920, mx: "auto" }}>
        <IconButton
          onClick={() => router.push("/admin/knowledge?tab=ai-instructions")}
          aria-label="Back"
          sx={{ mb: 1 }}
        >
          <ArrowBackIcon />
        </IconButton>
        <Alert
          severity="error"
          sx={{ mt: 2 }}
          action={
            <Button size="small" onClick={() => setRetryKey((k) => k + 1)}>
              Retry
            </Button>
          }
        >
          {loadError}
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 920, mx: "auto" }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <IconButton
          onClick={() => router.push("/admin/knowledge?tab=ai-instructions")}
          aria-label="Back"
        >
          <ArrowBackIcon />
        </IconButton>
        {!isNew && version !== null && (
          <Typography variant="caption" color="text.secondary">
            v{version}
          </Typography>
        )}
      </Stack>

      <PageHero
        icon={<PsychologyOutlinedIcon />}
        title={isNew ? "New AI instructions" : name}
        subtitle={description || undefined}
        cta={{
          label: saving ? "Saving..." : "Save",
          onClick: handleSave,
          icon: saving ? (
            <CircularProgress size={16} color="inherit" />
          ) : (
            <SaveIcon />
          ),
          disabled: saving || !name,
        }}
        data-testid="prompt-tuner-hero"
      />

      {saveError && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          onClose={() => setSaveError(null)}
        >
          {saveError}
        </Alert>
      )}

      <IdentitySection
        name={name}
        description={description}
        verification={verification}
        onNameChange={setName}
        onDescriptionChange={setDescription}
        onVerificationChange={setVerification}
      />

      <Box sx={{ mb: 2 }}>
        <SegmentedTabs
          tabs={[
            { id: "instructions", label: "Instructions" },
            { id: "output-format", label: "Output format" },
            {
              id: "teaching-examples",
              label: "Teaching examples",
              count: fewShotExamples.length,
            },
            ...(!isNew
              ? [
                  {
                    id: "test-it",
                    label: "Test it",
                    icon: <ScienceIcon sx={{ fontSize: 15 }} />,
                  },
                ]
              : []),
          ]}
          value={tab}
          onChange={setTab}
          aria-label="Prompt configuration tabs"
        />
      </Box>

      {tab === "instructions" && (
        <InstructionsTab
          loaded={loaded}
          isNew={isNew}
          systemPrompt={systemPrompt}
          improving={improving}
          aiSuggestion={aiSuggestion}
          editorRef={editorRef}
          onEditorChange={handleEditorChange}
          onAiImprove={handleAiImprove}
          onAcceptSuggestion={handleAcceptSuggestion}
          onDismissSuggestion={() => setAiSuggestion(null)}
        />
      )}

      {tab === "output-format" && (
        <OutputFormatTab
          outputSchema={outputSchema}
          onChange={setOutputSchema}
        />
      )}

      {tab === "teaching-examples" && (
        <TeachingExamplesTab
          examples={fewShotExamples}
          filteredExamples={filteredExamples}
          filterCat={filterCat}
          filterScope={filterScope}
          maxFewShot={maxFewShot}
          catCounts={catCounts}
          onFilterCat={setFilterCat}
          onFilterScope={setFilterScope}
          onMaxFewShot={setMaxFewShot}
          onAdd={addExample}
          onUpdate={updateExample}
          onRemove={removeExample}
        />
      )}

      {tab === "test-it" && !isNew && (
        <SandboxTab
          presets={presets}
          sandboxText={sandboxText}
          sandboxPresetId={sandboxPresetId}
          sandboxProvider={sandboxProvider}
          sandboxTier={sandboxTier}
          sandboxDryRun={sandboxDryRun}
          sandboxRunning={sandboxRunning}
          sandboxError={sandboxError}
          sandboxResult={sandboxResult}
          onSandboxText={setSandboxText}
          onSandboxPresetId={setSandboxPresetId}
          onSandboxProvider={setSandboxProvider}
          onSandboxTier={setSandboxTier}
          onSandboxDryRun={setSandboxDryRun}
          onClearError={() => setSandboxError(null)}
          onRun={handleSandboxRun}
        />
      )}

      <Snackbar
        open={saveSuccess}
        autoHideDuration={3000}
        onClose={() => setSaveSuccess(false)}
        message="Saved"
      />
    </Box>
  );
}
