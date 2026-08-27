/**
 * State and actions for Teach this form.
 *
 * Atlas trace: DI-5C9CA57B
 */
import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import {
  detectFormName,
  type FormSchemaItem,
  type FormSchemaSection,
} from "./formSchemaDetector";
import {
  detectFailureMessage,
  emptySection,
  isIncompleteSchema,
  localDetectOrEmpty,
  savedSchemaBlocksAutoDetect,
} from "./formSchemaTeach";

const FETCH_HDRS = { "X-Requested-With": "XMLHttpRequest" };

export function useFormSchemaTeach(
  fingerprint: string,
  sourceText: string,
  formName: string,
  onSaved?: () => void,
) {
  const [sections, setSections] = useState<FormSchemaSection[]>([]);
  const [name, setName] = useState(formName);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const loadOrDetect = useCallback(async () => {
    setLoading(true);
    setError("");
    const saved = await loadSaved(fingerprint);
    if (saved && savedSchemaBlocksAutoDetect(saved.sections)) {
      setName(saved.form_name);
      setSections(saved.sections);
      setSaved(true);
      return;
    }
    if (saved) setName(saved.form_name);
    const next = await detectWithFallback(sourceText, setError);
    const detectedName = detectFormName(sourceText);
    if (!saved?.form_name || saved.form_name === "Referral form") {
      if (detectedName && detectedName !== "Referral form") setName(detectedName);
    }
    if (!isIncompleteSchema(next)) {
      setSections(next);
      return;
    }
    setSections(next.length ? next : saved?.sections ?? []);
  }, [fingerprint, sourceText]);

  const retryDetect = useCallback(async () => {
    setLoading(true);
    setError("");
    setSaved(false);
    try {
      const next = await detectWithFallback(sourceText, setError);
      setSections(next);
    } finally {
      setLoading(false);
    }
  }, [sourceText]);

  useEffect(() => {
    void loadOrDetect().finally(() => setLoading(false));
  }, [loadOrDetect]);

  return bindTeachActions({
    fingerprint,
    name,
    sections,
    onSaved,
    setName,
    setSections,
    setSaving,
    setError,
    setSaved,
    loading,
    saving,
    error,
    saved,
    retryDetect,
  });
}

function bindTeachActions(state: {
  fingerprint: string;
  name: string;
  sections: FormSchemaSection[];
  onSaved?: () => void;
  setName: (name: string) => void;
  setSections: Dispatch<SetStateAction<FormSchemaSection[]>>;
  setSaving: (v: boolean) => void;
  setError: (v: string) => void;
  setSaved: (v: boolean) => void;
  loading: boolean;
  saving: boolean;
  error: string;
  saved: boolean;
  retryDetect: () => Promise<void>;
}) {
  return {
    sections: state.sections,
    name: state.name,
    setName: state.setName,
    loading: state.loading,
    saving: state.saving,
    error: state.error,
    saved: state.saved,
    setSaved: state.setSaved,
    retryDetect: state.retryDetect,
    addSection: () => {
      state.setSections((prev) => [...prev, emptySection(prev.length)]);
      state.setSaved(false);
    },
    saveSchema: () =>
      void saveSchema({
        fingerprint: state.fingerprint,
        name: state.name,
        sections: state.sections,
        onSaved: state.onSaved,
        setSaving: state.setSaving,
        setError: state.setError,
        setSaved: state.setSaved,
      }),
    patchSection: (idx: number, patch: Partial<FormSchemaSection>) => {
      state.setSections((prev) =>
        prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)),
      );
      state.setSaved(false);
    },
    removeSection: (idx: number) => {
      state.setSections((prev) => prev.filter((_, i) => i !== idx));
      state.setSaved(false);
    },
    patchItem: makePatchItem(state.setSections, state.setSaved),
    addItem: makeAddItem(state.setSections),
    addItemWithContent: makeAddItemWithContent(state.setSections, state.setSaved),
    removeItem: makeRemoveItem(state.setSections, state.setSaved),
  };
}

function makePatchItem(
  setSections: Dispatch<SetStateAction<FormSchemaSection[]>>,
  setSaved: (saved: boolean) => void,
) {
  return (sIdx: number, iIdx: number, patch: Partial<FormSchemaItem>) => {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return {
          ...s,
          items: s.items.map((item, j) =>
            j === iIdx ? { ...item, ...patch } : item,
          ),
        };
      }),
    );
    setSaved(false);
  };
}

function makeAddItemWithContent(
  setSections: Dispatch<SetStateAction<FormSchemaSection[]>>,
  setSaved: (saved: boolean) => void,
) {
  return (sIdx: number, item: FormSchemaItem) => {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return { ...s, items: [...s.items, item] };
      }),
    );
    setSaved(false);
  };
}

function makeAddItem(
  setSections: Dispatch<SetStateAction<FormSchemaSection[]>>,
) {
  return (sIdx: number) => {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return {
          ...s,
          items: [
            ...s.items,
            {
              pattern: "",
              entity_text: "",
              semantic_tag: "finding",
              assertion: "present",
            },
          ],
        };
      }),
    );
  };
}

function makeRemoveItem(
  setSections: Dispatch<SetStateAction<FormSchemaSection[]>>,
  setSaved: (saved: boolean) => void,
) {
  return (sIdx: number, iIdx: number) => {
    setSections((prev) =>
      prev.map((s, i) => {
        if (i !== sIdx) return s;
        return { ...s, items: s.items.filter((_, j) => j !== iIdx) };
      }),
    );
    setSaved(false);
  };
}

async function saveSchema(args: {
  fingerprint: string;
  name: string;
  sections: FormSchemaSection[];
  onSaved?: () => void;
  setSaving: (v: boolean) => void;
  setError: (v: string) => void;
  setSaved: (v: boolean) => void;
}): Promise<void> {
  args.setSaving(true);
  args.setError("");
  try {
    const res = await fetch(`/api/form-schemas/${args.fingerprint}`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...FETCH_HDRS },
      body: JSON.stringify({
        form_name: args.name,
        sections: args.sections,
        saved_by: "validation_lab",
      }),
    });
    if (!res.ok) throw new Error("save");
    args.setSaved(true);
    args.onSaved?.();
  } catch {
    args.setError("Could not save the form schema. Try again.");
  } finally {
    args.setSaving(false);
  }
}

async function loadSaved(
  fingerprint: string,
): Promise<{ form_name: string; sections: FormSchemaSection[] } | null> {
  try {
    const existing = await fetch(`/api/form-schemas/${fingerprint}`, {
      credentials: "include",
      headers: FETCH_HDRS,
    });
    if (!existing.ok) return null;
    const payload = (await existing.json()) as {
      schema: { form_name: string; sections: FormSchemaSection[] } | null;
    };
    return payload.schema;
  } catch {
    return null;
  }
}

async function detectWithFallback(
  sourceText: string,
  setError: (msg: string) => void,
): Promise<FormSchemaSection[]> {
  const detected = await tryDetect(sourceText, setError);
  if (!isIncompleteSchema(detected)) {
    setError("");
    return detected;
  }
  const local = localDetectOrEmpty(sourceText);
  if (!isIncompleteSchema(local)) {
    setError("");
    return local;
  }
  return detected.length ? detected : local;
}

async function tryDetect(
  sourceText: string,
  setError: (msg: string) => void,
): Promise<FormSchemaSection[]> {
  try {
    const detect = await fetch("/api/form-schemas/detect", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...FETCH_HDRS },
      body: JSON.stringify({ text: sourceText }),
    });
    if (!detect.ok) {
      setError(detectFailureMessage(detect.status));
      return [];
    }
    const payload = (await detect.json()) as { sections: FormSchemaSection[] };
    return payload.sections ?? [];
  } catch {
    setError("We could not reach LEO. Add a section, or try again.");
    return [];
  }
}
