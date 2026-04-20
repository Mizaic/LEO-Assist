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
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SaveIcon from "@mui/icons-material/Save";
import ScienceIcon from "@mui/icons-material/Science";

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

  const [tab, setTab] = useState(0);
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
      .catch(() => setLoaded(true));
  }, [promptId, isNew]);

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
      }
    } catch {
      /* surfaced via TODO: toast in next pass */
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

  return (
    <Box sx={{ p: 3, maxWidth: 920, mx: "auto" }}>
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
        <IconButton
          onClick={() => router.push("/admin/knowledge?tab=ai-instructions")}
          aria-label="Back"
        >
          <ArrowBackIcon />
        </IconButton>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" fontWeight={700}>
            {isNew ? "New AI instructions" : "Edit AI instructions"}
          </Typography>
          {!isNew && version !== null && (
            <Typography variant="caption" color="text.secondary">
              v{version}
            </Typography>
          )}
        </Box>
        <Button
          variant="contained"
          startIcon={
            saving ? (
              <CircularProgress size={16} color="inherit" />
            ) : (
              <SaveIcon />
            )
          }
          onClick={handleSave}
          disabled={saving || !name}
        >
          {saving ? "Saving..." : "Save"}
        </Button>
      </Stack>

      <IdentitySection
        name={name}
        description={description}
        verification={verification}
        onNameChange={setName}
        onDescriptionChange={setDescription}
        onVerificationChange={setVerification}
      />

      <Tabs
        value={tab}
        onChange={(_, v) => setTab(v)}
        sx={{ mb: 0, borderBottom: "1px solid", borderColor: "divider" }}
      >
        <Tab label="Instructions" />
        <Tab label="Output format" />
        <Tab
          label={
            <Stack direction="row" alignItems="center" spacing={0.75}>
              <span>Teaching examples</span>
              <Chip
                size="small"
                label={`${fewShotExamples.length} (${coreCount} core)`}
                sx={{
                  height: 18,
                  fontSize: "0.68rem",
                  bgcolor:
                    fewShotExamples.length > 0 ? "primary.100" : "grey.200",
                  color:
                    fewShotExamples.length > 0
                      ? "primary.main"
                      : "text.disabled",
                }}
              />
            </Stack>
          }
        />
        <Tab
          disabled={isNew}
          label={
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <ScienceIcon sx={{ fontSize: 15 }} />
              <span>Test it</span>
            </Stack>
          }
        />
      </Tabs>

      {tab === 0 && (
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

      {tab === 1 && (
        <OutputFormatTab
          outputSchema={outputSchema}
          onChange={setOutputSchema}
        />
      )}

      {tab === 2 && (
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

      {tab === 3 && (
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
    </Box>
  );
}
