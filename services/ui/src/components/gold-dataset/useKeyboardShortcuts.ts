import { useEffect } from "react";

interface Shortcuts {
  enabled: boolean;
  onMarkGold?: () => void;
  onAcceptAll?: () => void;
  onNext?: () => void;
  onClose?: () => void;
  onToggleHelp?: () => void;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target instanceof HTMLInputElement) return true;
  if (target instanceof HTMLTextAreaElement) return true;
  if (target instanceof HTMLSelectElement) return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest('[role="combobox"]'));
}

export default function useKeyboardShortcuts({
  enabled,
  onMarkGold,
  onAcceptAll,
  onNext,
  onClose,
  onToggleHelp,
}: Shortcuts): void {
  useEffect(() => {
    if (!enabled) return undefined;
    function onKeyDown(event: KeyboardEvent) {
      if (isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if (key === "?") {
        event.preventDefault();
        onToggleHelp?.();
        return;
      }
      if (key === "escape") {
        event.preventDefault();
        onClose?.();
        return;
      }
      if (key === "a") {
        event.preventDefault();
        onAcceptAll?.();
        return;
      }
      if (key === "n") {
        event.preventDefault();
        onNext?.();
        return;
      }
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey || !isEditableTarget(event.target))) {
        event.preventDefault();
        onMarkGold?.();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled, onAcceptAll, onClose, onMarkGold, onNext, onToggleHelp]);
}
