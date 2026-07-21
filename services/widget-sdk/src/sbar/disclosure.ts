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
      date: s.date ?? null,
    }));
  }
  return (part.sourceIds || []).map((id) => ({
    id,
    label: formatSourceLabel(id),
    preview: "",
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
          const title = src.preview
            ? `${label} -- ${src.preview}`
            : src.id;
          return (
            '<button type="button" class="leo-source-chip" ' +
            `data-source-id="${_escape(src.id)}" data-stage="${stage}" ` +
            `data-source-label="${_escape(label)}" ` +
            `title="${_escape(title)}" ` +
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

function _openSourceDialog(
  root: ParentNode,
  title: string,
  body: string,
  sourceId: string,
): void {
  const host =
    root instanceof ShadowRoot
      ? root
      : (root as Document).body || (root as HTMLElement);
  const existing = (host as ParentNode).querySelector?.(".leo-source-dialog");
  existing?.remove();
  const dialog = document.createElement("div");
  dialog.className = "leo-source-dialog";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("data-testid", "leo-source-dialog");
  dialog.innerHTML =
    `<div class="leo-source-dialog-card">` +
    `<header class="leo-source-dialog-header">` +
    `<strong>${_escape(title)}</strong>` +
    `<button type="button" class="leo-source-dialog-close" aria-label="Close">` +
    `Close</button></header>` +
    `<p class="leo-source-dialog-meta">Technical id: ${_escape(sourceId)}</p>` +
    `<pre class="leo-source-dialog-body">${_escape(body)}</pre>` +
    `</div>`;
  const close = () => dialog.remove();
  dialog
    .querySelector(".leo-source-dialog-close")
    ?.addEventListener("click", close);
  dialog.addEventListener("click", (ev) => {
    if (ev.target === dialog) close();
  });
  (host as HTMLElement | ShadowRoot).appendChild(dialog);
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
      callbacks.onSourceClicked({ stage, sourceId, label });
      const preview = chip.getAttribute("title") || label || sourceId;
      _openSourceDialog(root, label || sourceId, preview, sourceId);
    }
  }

  const node = root as unknown as EventTarget;
  node.addEventListener("click", onClick);
  return () => node.removeEventListener("click", onClick);
}
