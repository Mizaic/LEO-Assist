/**
 * Source-record disclosure renderer.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (acceptance criterion 1 - both variants render
 *       byte-identical disclosure markup for the same payload)
 *   DI: DI-5F121122 (disclosure-engagement telemetry feeds off the
 *       open / close / source-id-clicked events emitted here)
 *   Risk mitigated: R-4965BCD2 (the disclosure is the safety control
 *       that lets the reviewing clinician verify each Background claim
 *       against the original encounter records)
 *
 * SHARED ACROSS BOTH VARIANTS: this module is imported unchanged by
 * both the Shadow-DOM web component and the iframe shell. The exact
 * same DOM structure and class names are emitted regardless of which
 * trust boundary the host chose. That is what makes acceptance
 * criterion 1 of DI-85C95E53 ("byte-identical rendering of the
 * source-record disclosure given the same assessment payload") true
 * by construction rather than by parallel implementation.
 */

import type { SbarBackgroundPart, SbarStageName } from "../data/types";

export interface DisclosureCallbacks {
  onOpen(part: { stage: SbarStageName }): void;
  onClose(part: { stage: SbarStageName }): void;
  onSourceClicked(payload: { stage: SbarStageName; sourceId: string }): void;
}

interface DisclosureProps {
  stage: SbarStageName;
  parts: SbarBackgroundPart[];
}

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
      const chips = p.sourceIds
        .map(
          (id) =>
            '<button type="button" class="leo-source-chip" ' +
            `data-source-id="${_escape(id)}" data-stage="${stage}" ` +
            `aria-label="Open source record ${_escape(id)}">` +
            `${_escape(id)}</button>`,
        )
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

/**
 * Wire toggle + chip click handlers on a rendered disclosure subtree.
 * The root argument is the container that holds the disclosure markup
 * (a shadow root for the web-component variant, document.body for the
 * iframe variant). Returns a teardown callback.
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
      callbacks.onSourceClicked({ stage, sourceId });
    }
  }

  const node = root as unknown as EventTarget;
  node.addEventListener("click", onClick);
  return () => node.removeEventListener("click", onClick);
}
