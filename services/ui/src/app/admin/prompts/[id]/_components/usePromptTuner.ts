/**
 * Atlas trace:
 *   DO: DO-83EBEE2C
 *   DI: DI-B954388C
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import type { MarkdownEditorHandle } from "@/components/markdown-editor";
import { api } from "@/lib/api";

import {
  blankExample,
  EMPTY_FORM,
  EMPTY_SANDBOX,
  EMPTY_UI,
  exampleCatCounts,
  filterExamples,
  formFromPrompt,
  type PromptForm,
  type PromptUi,
  type SandboxUi,
} from "./promptTunerState";
import type {
  FewShotExample,
  PresetItem,
  PromptConfigData,
  SandboxResult,
} from "./types";

export function usePromptTuner() {
  const params = useParams();
  const router = useRouter();
  const promptId = params.id as string;
  const isNew = promptId === "new";
  const editorRef = useRef<MarkdownEditorHandle>(null);
  const [form, setForm] = useState<PromptForm>(EMPTY_FORM);
  const [ui, setUi] = useState<PromptUi>({ ...EMPTY_UI, loaded: isNew });
  const [sandbox, setSandbox] = useState<SandboxUi>(EMPTY_SANDBOX);
  const [presets, setPresets] = useState<PresetItem[]>([]);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    api
      .get<{ presets: PresetItem[] }>("/api/presets")
      .then((data) => setPresets(data.presets || []))
      .catch(() => {
        /* presets unavailable -- fall back to custom */
      });
  }, []);

  usePromptLoad(promptId, isNew, retryKey, setForm, setUi);

  const goBack = useCallback(() => {
    router.push("/admin/knowledge?tab=ai-instructions");
  }, [router]);
  const actions = usePromptActions({
    promptId,
    isNew,
    router,
    editorRef,
    form,
    setForm,
    setUi,
    sandbox,
    setSandbox,
  });

  return {
    promptId,
    isNew,
    editorRef,
    form,
    setForm,
    ui,
    setUi,
    sandbox,
    setSandbox,
    presets,
    goBack,
    retry: () => setRetryKey((k) => k + 1),
    filteredExamples: filterExamples(
      form.fewShotExamples,
      ui.filterCat,
      ui.filterScope,
    ),
    catCounts: exampleCatCounts(form.fewShotExamples),
    coreCount: form.fewShotExamples.filter((ex) => ex.core).length,
    maxFewShot: form.maxFewShot,
    ...actions,
  };
}

function usePromptLoad(
  promptId: string,
  isNew: boolean,
  retryKey: number,
  setForm: (next: PromptForm) => void,
  setUi: React.Dispatch<React.SetStateAction<PromptUi>>,
) {
  useEffect(() => {
    if (isNew) {
      setUi((u) => ({ ...u, loaded: true, loadError: null }));
      return;
    }
    setUi((u) => ({ ...u, loaded: false, loadError: null }));
    api
      .get<PromptConfigData>(`/api/prompts/${promptId}`)
      .then((data) => {
        setForm(formFromPrompt(data));
        setUi((u) => ({ ...u, loaded: true }));
      })
      .catch(() => {
        setUi((u) => ({
          ...u,
          loaded: true,
          loadError: "Failed to load. Please try again.",
        }));
      });
  }, [promptId, isNew, retryKey, setForm, setUi]);
}

function usePromptActions(args: {
  promptId: string;
  isNew: boolean;
  router: ReturnType<typeof useRouter>;
  editorRef: React.RefObject<MarkdownEditorHandle | null>;
  form: PromptForm;
  setForm: React.Dispatch<React.SetStateAction<PromptForm>>;
  setUi: React.Dispatch<React.SetStateAction<PromptUi>>;
  sandbox: SandboxUi;
  setSandbox: React.Dispatch<React.SetStateAction<SandboxUi>>;
}) {
  const save = usePromptSave(args);
  const examples = usePromptExamples(args.setForm);
  const improve = usePromptImprove(args.form, args.editorRef, args.setForm, args.setUi);
  const runSandbox = usePromptSandbox(args);
  return { ...save, ...examples, ...improve, ...runSandbox };
}

function usePromptSave(args: {
  promptId: string;
  isNew: boolean;
  router: ReturnType<typeof useRouter>;
  editorRef: React.RefObject<MarkdownEditorHandle | null>;
  form: PromptForm;
  setUi: React.Dispatch<React.SetStateAction<PromptUi>>;
}) {
  const { promptId, isNew, router, editorRef, form, setUi } = args;
  const handleSave = useCallback(async () => {
    setUi((u) => ({ ...u, saving: true, saveError: null }));
    const payload = {
      name: form.name,
      description: form.description,
      systemPrompt: editorRef.current?.getMarkdown() ?? form.systemPrompt,
      outputSchema: form.outputSchema,
      verification: form.verification,
      fewShotExamples: form.fewShotExamples,
      maxFewShot: form.maxFewShot,
    };
    try {
      if (isNew) {
        const result = await api.post<{ id: string }>("/api/prompts", payload);
        router.push(`/admin/prompts/${result.id}`);
      } else {
        await api.put(`/api/prompts/${promptId}`, payload);
        setUi((u) => ({ ...u, saveSuccess: true }));
      }
    } catch {
      setUi((u) => ({ ...u, saveError: "Save failed. Please try again." }));
    } finally {
      setUi((u) => ({ ...u, saving: false }));
    }
  }, [form, editorRef, isNew, promptId, router, setUi]);
  return { handleSave };
}

function usePromptExamples(
  setForm: React.Dispatch<React.SetStateAction<PromptForm>>,
) {
  const addExample = useCallback(() => {
    setForm((f) => ({ ...f, fewShotExamples: [...f.fewShotExamples, blankExample()] }));
  }, [setForm]);
  const removeExample = useCallback((id: string) => {
    setForm((f) => ({
      ...f,
      fewShotExamples: f.fewShotExamples.filter((e) => e.id !== id),
    }));
  }, [setForm]);
  const updateExample = useCallback(
    (id: string, field: keyof FewShotExample, value: string | boolean) => {
      setForm((f) => ({
        ...f,
        fewShotExamples: f.fewShotExamples.map((e) =>
          e.id === id ? { ...e, [field]: value } : e,
        ),
      }));
    },
    [setForm],
  );
  return { addExample, removeExample, updateExample };
}

function usePromptImprove(
  form: PromptForm,
  editorRef: React.RefObject<MarkdownEditorHandle | null>,
  setForm: React.Dispatch<React.SetStateAction<PromptForm>>,
  setUi: React.Dispatch<React.SetStateAction<PromptUi>>,
) {
  const handleAiImprove = useCallback(async () => {
    setUi((u) => ({ ...u, improving: true }));
    try {
      const result = await api.post<{ improvedPrompt: string }>(
        "/api/prompts/improve",
        { currentPrompt: form.systemPrompt, outputSchema: form.outputSchema },
      );
      setUi((u) => ({ ...u, aiSuggestion: result.improvedPrompt }));
    } catch {
      setUi((u) => ({ ...u, aiSuggestion: null }));
    } finally {
      setUi((u) => ({ ...u, improving: false }));
    }
  }, [form.systemPrompt, form.outputSchema, setUi]);

  const handleAcceptSuggestion = useCallback((suggestion: string) => {
    editorRef.current?.setMarkdown(suggestion);
    setForm((f) => ({ ...f, systemPrompt: suggestion }));
    setUi((u) => ({ ...u, aiSuggestion: null }));
  }, [editorRef, setForm, setUi]);

  const handleEditorChange = useCallback((md: string) => {
    setForm((f) => ({ ...f, systemPrompt: md }));
  }, [setForm]);

  return { handleAiImprove, handleAcceptSuggestion, handleEditorChange };
}

function usePromptSandbox(args: {
  promptId: string;
  isNew: boolean;
  sandbox: SandboxUi;
  setSandbox: React.Dispatch<React.SetStateAction<SandboxUi>>;
}) {
  const { promptId, isNew, sandbox, setSandbox } = args;
  const handleSandboxRun = useCallback(async () => {
    if (!sandbox.text.trim() || isNew) return;
    setSandbox((s) => ({ ...s, running: true, error: null, result: null }));
    try {
      const payload: Record<string, unknown> = {
        encounterText: sandbox.text,
        dryRun: sandbox.dryRun,
      };
      if (sandbox.presetId && sandbox.presetId !== "__custom__") {
        payload.presetId = sandbox.presetId;
      } else {
        payload.provider = sandbox.provider;
        payload.tier = sandbox.tier;
      }
      const result = await api.post(`/api/prompts/${promptId}/simulate`, payload);
      setSandbox((s) => ({ ...s, result: result as SandboxResult }));
    } catch (err: unknown) {
      setSandbox((s) => ({
        ...s,
        error: err instanceof Error ? err.message : "Simulation failed",
      }));
    } finally {
      setSandbox((s) => ({ ...s, running: false }));
    }
  }, [sandbox, isNew, promptId, setSandbox]);
  return { handleSandboxRun };
}

export function patchForm<K extends keyof PromptForm>(
  setForm: React.Dispatch<React.SetStateAction<PromptForm>>,
  key: K,
  value: PromptForm[K],
) {
  setForm((f) => ({ ...f, [key]: value }));
}

export function patchSandbox<K extends keyof SandboxUi>(
  setSandbox: React.Dispatch<React.SetStateAction<SandboxUi>>,
  key: K,
  value: SandboxUi[K],
) {
  setSandbox((s) => ({ ...s, [key]: value }));
}

export type PromptTuner = ReturnType<typeof usePromptTuner>;
