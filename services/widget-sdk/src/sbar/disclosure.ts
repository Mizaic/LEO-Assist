/**
 * Source-record disclosure renderer.
 *
 * Atlas trace:
 *   DI: DI-85C95E53, DI-A898556B
 *   Risk mitigated: R-4965BCD2
 */

import type {
  SbarBackgroundPart,
  SbarSourceRef,
  SbarStageName,
} from "../data/types";

export interface DisclosureCallbacks {
  onOpen(part: { stage: SbarStageName }): void;
  onClose(part: { stage: SbarStageName }): void;
  onSourceClicked(payload: {
    stage: SbarStageName;
    sourceId: string;
    label?: string;
  }): void;
  /**
   * Optional live lookup for a source record's exact text when the
   * chip has no persisted ``fullText`` (Assessments generated before
   * that field existed). The dialog opens immediately with whatever
   * is already on the chip, then upgrades in place if this resolves
   * with non-empty text. Returning null/undefined or rejecting keeps
   * the short-preview fallback.
   */
  resolveSourceText?(sourceId: string): Promise<string | null | undefined>;
}

interface DisclosureProps {
  stage: SbarStageName;
  parts: SbarBackgroundPart[];
}

const UUID_PREFIX_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:/i;

function _formatRecordRange(start: number, end: number): string {
  if (start <= 0 || end <= 0) return "no records";
  if (start === end) return `record ${start}`;
  return `records ${start}-${end}`;
}

function _partLabel(part: SbarBackgroundPart): string {
  const range = _formatRecordRange(
    part.recordRange?.[0] ?? 0,
    part.recordRange?.[1] ?? 0,
  );
  return `Part ${part.index} of ${part.total} -- ${range}`;
}

function _escape(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Clinician-facing label; keeps raw id on data-source-id. */
export function formatSourceLabel(id: string, typeHint = ""): string {
  const text = String(id || "").trim();
  if (!text) return typeHint || "Clinical record";
  const stripped = text.replace(UUID_PREFIX_RE, "");
  const parts = stripped.split(":");
  if (parts.length >= 2 && stripped !== text) {
    const label = parts.slice(0, -1).join(":");
    const kind = parts[parts.length - 1];
    return `${label} (${kind})`;
  }
  if (typeHint) {
    const short =
      stripped.length <= 24
        ? stripped
        : `${stripped.slice(0, 10)}...${stripped.slice(-6)}`;
    return `${typeHint}: ${short}`;
  }
  if (stripped.length > 28) {
    return `Clinical record (${stripped.slice(0, 8)}...)`;
  }
  return stripped;
}

function _resolveSources(part: SbarBackgroundPart): SbarSourceRef[] {
  if (Array.isArray(part.sources) && part.sources.length > 0) {
    return part.sources.map((s) => ({
      id: s.id,
      type: s.type,
      label: s.label || formatSourceLabel(s.id, s.type || ""),
      preview: s.preview || "",
      fullText: s.fullText || "",
      date: s.date ?? null,
    }));
  }
  return (part.sourceIds || []).map((id) => ({
    id,
    label: formatSourceLabel(id),
    preview: "",
    fullText: "",
  }));
}

/**
 * Build the deterministic HTML markup for a source-record disclosure
 * panel. Returns an empty string when the payload contains no source
 * IDs - reviewers should never see a "Show source records (0)" UI.
 */
export function renderDisclosureHtml({ stage, parts }: DisclosureProps): string {
  const totalIds = parts.reduce((acc, p) => acc + p.sourceIds.length, 0);
  if (totalIds === 0) return "";
  const partRows = parts
    .filter((p) => p.sourceIds.length > 0)
    .map((p, i) => {
      const sources = _resolveSources(p);
      const chips = sources
        .map((src) => {
          const label = src.label || formatSourceLabel(src.id, src.type || "");
          const hoverPreview = src.preview
            ? `${label} -- ${src.preview}`
            : src.id;
          const fullText = src.fullText || "";
          return (
            '<button type="button" class="leo-source-chip" ' +
            `data-source-id="${_escape(src.id)}" data-stage="${stage}" ` +
            `data-source-label="${_escape(label)}" ` +
            `data-source-preview="${_escape(src.preview || "")}" ` +
            `data-source-full-text="${_escape(fullText)}" ` +
            `title="${_escape(hoverPreview)}" ` +
            `aria-label="Open source record ${_escape(label)}">` +
            `${_escape(label)}</button>`
          );
        })
        .join("");
      const failedSuffix =
        p.status === "failed" ? " -- this part did not finish" : "";
      return (
        `<div class="leo-source-part" ` +
        `data-testid="leo-disclosure-${stage}-part-${i}">` +
        `<span class="leo-source-part-label">${_escape(_partLabel(p))}` +
        `${_escape(failedSuffix)}</span>` +
        `<div class="leo-source-chips">${chips}</div>` +
        "</div>"
      );
    })
    .join("");
  return (
    `<div class="leo-disclosure" data-leo-disclosure="source-records" ` +
    `data-stage="${stage}" data-open="false" ` +
    `data-testid="leo-disclosure-${stage}">` +
    `<button type="button" class="leo-disclosure-toggle" ` +
    `data-leo-toggle="${stage}" aria-expanded="false" ` +
    `data-testid="leo-disclosure-${stage}-toggle">` +
    `Show source records (${totalIds})</button>` +
    `<div class="leo-disclosure-panel">${partRows}</div>` +
    "</div>"
  );
}

interface SourceDialogContent {
  title: string;
  sourceId: string;
  fullText: string;
  preview: string;
}

/**
 * Pick the dialog body + a short note about what the reviewer is
 * looking at. Prefers the exact record text the LLM saw; falls back
 * to the short preview for legacy Assessments that predate
 * ``full_text``, and finally to an explicit "nothing to show" state
 * rather than silently rendering an empty box.
 */
function _dialogBodyAndNote(
  content: Pick<SourceDialogContent, "fullText" | "preview">,
): {
  body: string;
  note: string;
} {
  if (content.fullText.trim()) {
    return {
      body: content.fullText,
      note: "Exact record text used to generate this section.",
    };
  }
  if (content.preview.trim()) {
    return {
      body: content.preview,
      note: "Short preview only -- the full record text is not available for this item.",
    };
  }
  return {
    body: "No extract is available for this record.",
    note: "",
  };
}

const _LOADING_NOTE = "Looking up the exact record text...";

/** Update an already-open dialog's body/note without tearing it down. */
function _setDialogState(
  dialog: HTMLElement,
  state: { body: string; note: string; loading?: boolean },
): void {
  const bodyEl = dialog.querySelector<HTMLElement>(
    '[data-testid="leo-source-dialog-body"]',
  );
  const noteEl = dialog.querySelector<HTMLElement>(
    '[data-testid="leo-source-dialog-note"]',
  );
  if (bodyEl) bodyEl.textContent = state.body;
  if (noteEl) {
    noteEl.textContent = state.note;
    noteEl.style.display = state.note ? "" : "none";
  }
  dialog.setAttribute("aria-busy", state.loading ? "true" : "false");
}

function _openSourceDialog(
  root: ParentNode,
  content: SourceDialogContent,
): HTMLElement {
  const host =
    root instanceof ShadowRoot
      ? root
      : (root as Document).body || (root as HTMLElement);
  const existing = (host as ParentNode).querySelector?.(".leo-source-dialog");
  existing?.remove();
  const { body, note } = _dialogBodyAndNote(content);
  const dialog = document.createElement("div");
  dialog.className = "leo-source-dialog";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("data-testid", "leo-source-dialog");
  dialog.setAttribute("data-source-id", content.sourceId);
  dialog.innerHTML =
    `<div class="leo-source-dialog-card">` +
    `<header class="leo-source-dialog-header">` +
    `<strong>${_escape(content.title)}</strong>` +
    `<button type="button" class="leo-source-dialog-close" aria-label="Close">` +
    `Close</button></header>` +
    `<p class="leo-source-dialog-meta">Technical id: ${_escape(content.sourceId)}</p>` +
    `<p class="leo-source-dialog-note" data-testid="leo-source-dialog-note" ` +
    `style="${note ? "" : "display:none"}">${_escape(note)}</p>` +
    `<pre class="leo-source-dialog-body" data-testid="leo-source-dialog-body">${_escape(body)}</pre>` +
    `</div>`;
  const close = () => dialog.remove();
  dialog
    .querySelector(".leo-source-dialog-close")
    ?.addEventListener("click", close);
  dialog.addEventListener("click", (ev) => {
    if (ev.target === dialog) close();
  });
  (host as HTMLElement | ShadowRoot).appendChild(dialog);
  return dialog;
}

/**
 * Kick off the live source-text lookup and upgrade the dialog in
 * place if it resolves before the reviewer closes/replaces it.
 * ``dialog.isConnected`` guards against updating a dialog that has
 * since been removed (closed, or superseded by a different chip).
 */
function _upgradeDialogWithLiveText(
  dialog: HTMLElement,
  sourceId: string,
  preview: string,
  resolveSourceText: (id: string) => Promise<string | null | undefined>,
): void {
  const { body: interimBody } = _dialogBodyAndNote({ fullText: "", preview });
  _setDialogState(dialog, { body: interimBody, note: _LOADING_NOTE, loading: true });
  resolveSourceText(sourceId)
    .then((liveText) => {
      if (!dialog.isConnected) return;
      const text = (liveText || "").trim();
      if (text) {
        _setDialogState(dialog, {
          body: text,
          note: "Exact record text retrieved from the patient record.",
        });
        return;
      }
      const fallback = _dialogBodyAndNote({ fullText: "", preview });
      _setDialogState(dialog, fallback);
    })
    .catch(() => {
      if (!dialog.isConnected) return;
      const fallback = _dialogBodyAndNote({ fullText: "", preview });
      _setDialogState(dialog, fallback);
    });
}

/**
 * Wire toggle + chip click handlers on a rendered disclosure subtree.
 */
export function attachDisclosureHandlers(
  root: ParentNode,
  callbacks: DisclosureCallbacks,
): () => void {
  function onClick(event: Event) {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const toggle = target.closest<HTMLElement>("[data-leo-toggle]");
    if (toggle) {
      const stage = toggle.getAttribute("data-leo-toggle") as SbarStageName;
      const wrapper = toggle.closest<HTMLElement>(".leo-disclosure");
      if (!wrapper) return;
      const isOpen = wrapper.getAttribute("data-open") === "true";
      const next = !isOpen;
      wrapper.setAttribute("data-open", next ? "true" : "false");
      toggle.setAttribute("aria-expanded", next ? "true" : "false");
      const label = next
        ? toggle.textContent?.replace(/^Show /, "Hide ")
        : toggle.textContent?.replace(/^Hide /, "Show ");
      if (label) toggle.textContent = label;
      if (next) callbacks.onOpen({ stage });
      else callbacks.onClose({ stage });
      return;
    }
    const chip = target.closest<HTMLElement>(".leo-source-chip");
    if (chip) {
      const stage = chip.getAttribute("data-stage") as SbarStageName;
      const sourceId = chip.getAttribute("data-source-id") ?? "";
      const label = chip.getAttribute("data-source-label") ?? undefined;
      const fullText = chip.getAttribute("data-source-full-text") || "";
      const preview = chip.getAttribute("data-source-preview") || "";
      callbacks.onSourceClicked({ stage, sourceId, label });
      const dialog = _openSourceDialog(root, {
        title: label || sourceId,
        sourceId,
        fullText,
        preview,
      });
      if (!fullText.trim() && callbacks.resolveSourceText) {
        _upgradeDialogWithLiveText(
          dialog,
          sourceId,
          preview,
          callbacks.resolveSourceText,
        );
      }
    }
  }

  const node = root as unknown as EventTarget;
  node.addEventListener("click", onClick);
  return () => node.removeEventListener("click", onClick);
}
