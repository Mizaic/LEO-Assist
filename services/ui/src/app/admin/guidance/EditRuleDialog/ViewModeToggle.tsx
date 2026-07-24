"use client";
/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */

/**
 * Three-way segmented control switching between the "Guided"
 * highlight-to-build wizard (HighlightWizard), the "Simple" sentence
 * canvas (SentenceEditor), and the "Advanced" boxed tree canvas
 * (LogicTreeEditor) for the rule logic editor. Persists the
 * reviewer's choice in localStorage so it sticks across rules; falls
 * back to the default when localStorage is unavailable (SSR, private
 * browsing, storage quota, etc.).
 */
import { useCallback, useEffect, useState } from "react";
import { SegmentedTabs } from "@leo/design-system";

export type EditorViewMode = "guided" | "simple" | "advanced";

const STORAGE_KEY = "leo.editRuleDialog.viewMode";

/**
 * Default view mode for reviewers with no stored preference. Guided
 * is the default per the highlight-to-build wizard plan -- most rules
 * in this dialog are anchored to a live NICE guideline sentence, and
 * the wizard is full parity with the tree/sentence canvases (it
 * mutates the exact same EditableLogicNode tree), so there is no
 * "Guided is a lesser mode" trade-off left to protect reviewers from.
 */
const DEFAULT_VIEW_MODE: EditorViewMode = "guided";

function isViewMode(value: unknown): value is EditorViewMode {
  return value === "guided" || value === "simple" || value === "advanced";
}

function readStoredMode(): EditorViewMode | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return isViewMode(raw) ? raw : null;
  } catch {
    return null;
  }
}

function writeStoredMode(mode: EditorViewMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // Private browsing / storage quota -- the toggle still works for
    // this session, it just won't persist across reloads.
  }
}

/**
 * Reads/writes the reviewer's Simple/Advanced preference. Starts at
 * the default on first render (so server and client markup match),
 * then syncs from localStorage in an effect.
 */
export function useViewMode(): [
  EditorViewMode,
  (mode: EditorViewMode) => void,
] {
  const [mode, setMode] = useState<EditorViewMode>(DEFAULT_VIEW_MODE);

  useEffect(() => {
    const stored = readStoredMode();
    if (stored) setMode(stored);
  }, []);

  const update = useCallback((next: EditorViewMode) => {
    setMode(next);
    writeStoredMode(next);
  }, []);

  return [mode, update];
}

const VIEW_MODE_TABS = [
  { id: "guided" as const, label: "Guided" },
  { id: "simple" as const, label: "Simple" },
  { id: "advanced" as const, label: "Advanced" },
];

interface Props {
  value: EditorViewMode;
  onChange: (mode: EditorViewMode) => void;
}

export default function ViewModeToggle({ value, onChange }: Props) {
  return (
    <SegmentedTabs
      tabs={VIEW_MODE_TABS}
      value={value}
      onChange={(id) => {
        if (isViewMode(id)) onChange(id);
      }}
      aria-label="Switch between the Guided wizard, the Simple sentence view, and the Advanced tree view"
      dense
    />
  );
}
