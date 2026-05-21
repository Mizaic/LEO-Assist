/**
 * Shared SBAR surface renderer for both widget variants.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (one source tree, two variants identical)
 *   DI: DI-85944331 (locked LEO-by-Mizaic branding inside the boundary)
 *   Risk mitigated: R-4965BCD2 (every Background section gets a
 *                  source-record disclosure)
 *
 * SCOPE NOTE FOR SLICE 1 OF THE WIDGET MVP:
 * This module renders the stage cards + the safety-critical
 * source-record disclosure as a vanilla DOM template. It is byte-
 * compatible with the SBAR pipeline wire shape (SbarSection,
 * SbarBackgroundPart). A follow-up DO will replace the body
 * rendering with the in-app SbarFinalView once SbarFinalView and
 * MarkdownEditor have been hoisted out of services/ui into a
 * publishable package - until then, importing them transitively
 * pulls Next.js path aliases into the SDK bundle, which we are not
 * willing to ship inside a Class B medical-device widget without
 * separate DI / Risk review.
 *
 * For the DI-85C95E53 acceptance criteria the contract that matters
 * is: "byte-identical rendering of the source-record disclosure
 * given the same assessment payload" between the two variants. Both
 * variants import this file unchanged; that AC is met by
 * construction.
 */

import type {
  CompletenessFinding,
  GuidelineMatch,
  SbarAssessmentPayload,
  SbarBackgroundPart,
  SbarSection,
  SbarStageName,
} from "../data/types";
import { LEO_EVENT_NAMES } from "../data/types";
import { MIZAIC_MARK_SVG } from "../branding/tokens";
import { splitFinalSbar, stripSourceComments } from "./split";
import { attachDisclosureHandlers, renderDisclosureHtml } from "./disclosure";

const STAGE_LABELS: Record<SbarStageName, string> = {
  situation: "Situation",
  background: "Background",
  assessment: "Assessment",
  recommendation: "Recommendation",
};

export interface SurfaceEvent {
  type: (typeof LEO_EVENT_NAMES)[keyof typeof LEO_EVENT_NAMES];
  detail: {
    assessmentId: string;
    stage?: SbarStageName;
    sourceId?: string;
    missingFields?: string[];
    unclearFields?: string[];
  };
}

export interface RenderSurfaceOptions {
  payload: SbarAssessmentPayload;
  /** Optional active LEO clinical safety advisory banner text. */
  advisory?: string | null;
  /** Channel for emitting widget events (variant-agnostic). */
  emit(event: SurfaceEvent): void;
}

function _escape(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function _renderStage(
  section: SbarSection,
  partsByStage: Record<SbarStageName, SbarBackgroundPart[]>,
): string {
  const cleaned = stripSourceComments(section.body);
  const disclosure = renderDisclosureHtml({
    stage: section.stage,
    parts: partsByStage[section.stage] ?? [],
  });
  return (
    `<section class="leo-stage" data-stage="${section.stage}" ` +
    `data-testid="leo-stage-${section.stage}">` +
    `<header class="leo-stage-header">${STAGE_LABELS[section.stage]}</header>` +
    `<div class="leo-stage-body">${_escape(cleaned)}</div>` +
    disclosure +
    "</section>"
  );
}

function _renderHeader(payload: SbarAssessmentPayload): string {
  return (
    '<header class="leo-header" data-testid="leo-header">' +
    `<span class="leo-mark">${MIZAIC_MARK_SVG}</span>` +
    '<span class="leo-product">LEO by Mizaic</span>' +
    '<span class="leo-test-only" data-testid="leo-test-only-banner">' +
    "Test only -- not for clinical use</span>" +
    "</header>"
  );
}

function _renderAdvisory(advisory: string | null | undefined): string {
  if (!advisory) return "";
  return (
    `<div class="leo-advisory" role="alert" ` +
    `data-testid="leo-advisory">${_escape(advisory)}</div>`
  );
}

function _renderCompletenessPanel(
  finding: CompletenessFinding | null | undefined,
): string {
  if (!finding) return "";
  const items: string[] = [
    ...finding.presentFields.map(
      (f) =>
        `<li class="leo-field leo-field--present" data-testid="leo-field-present">${_escape(f)}</li>`,
    ),
    ...finding.missingFields.map(
      (f) =>
        `<li class="leo-field leo-field--missing" data-testid="leo-field-missing">${_escape(f)}</li>`,
    ),
    ...finding.unclearFields.map(
      (f) =>
        `<li class="leo-field leo-field--unclear" data-testid="leo-field-unclear">${_escape(f)}</li>`,
    ),
  ];
  if (items.length === 0) return "";
  return (
    `<section class="leo-completeness" data-testid="leo-completeness">` +
    `<header class="leo-stage-header">Referral completeness</header>` +
    `<ul class="leo-field-list">${items.join("")}</ul>` +
    `</section>`
  );
}

function _renderGuidelineMatches(matches: GuidelineMatch[] | undefined): string {
  if (!matches || matches.length === 0) return "";
  const items = matches.map((m) => {
    const verbatim = m.recommendationVerbatim
      ? `<details class="leo-verbatim" data-testid="leo-verbatim-details">` +
        `<summary class="leo-verbatim-toggle">Source text</summary>` +
        `<p class="leo-verbatim-text">${_escape(m.recommendationVerbatim)}</p>` +
        `</details>`
      : "";
    return (
      `<li class="leo-guideline-match" data-testid="leo-guideline-match">` +
      `<span class="leo-guideline-name">${_escape(m.name)}</span>` +
      `<span class="leo-guideline-strength leo-guideline-strength--${_escape(m.strength)}">${_escape(m.strength)}</span>` +
      verbatim +
      `</li>`
    );
  });
  return (
    `<section class="leo-guideline-matches" data-testid="leo-guideline-matches">` +
    `<header class="leo-stage-header">Matched guidelines</header>` +
    `<ul class="leo-guideline-list">${items.join("")}</ul>` +
    `</section>`
  );
}

function _emitCompletenessEvents(
  payload: SbarAssessmentPayload,
  emit: (e: SurfaceEvent) => void,
): void {
  const finding = payload.completenessFinding;
  if (finding == null) {
    emit({
      type: LEO_EVENT_NAMES.completenessUnavailable,
      detail: { assessmentId: payload.assessmentId },
    });
    return;
  }
  const hasMissing = finding.missingFields.length > 0;
  const hasUnclear = finding.unclearFields.length > 0;
  if (hasMissing || hasUnclear) {
    emit({
      type: LEO_EVENT_NAMES.completenessIncomplete,
      detail: {
        assessmentId: payload.assessmentId,
        missingFields: finding.missingFields,
        unclearFields: finding.unclearFields,
      },
    });
  }
}

/**
 * Render the LEO surface into the given root, wire interaction
 * handlers, and return a teardown callback. The root MUST be a node
 * inside the trust boundary (a shadow root for the web component, or
 * document.body inside the iframe shell).
 */
export function renderSurface(
  root: ParentNode & Node,
  options: RenderSurfaceOptions,
): () => void {
  const { payload, emit, advisory } = options;

  // Emit completeness events before any DOM mutation so the host can
  // intercept and show a confirmation dialog before the widget paints.
  _emitCompletenessEvents(payload, emit);

  const sections = splitFinalSbar(payload.markdown ?? "");
  const partsByStage: Record<SbarStageName, SbarBackgroundPart[]> = {
    situation: [],
    background: payload.backgroundParts ?? [],
    assessment: [],
    recommendation: [],
  };

  let inner = "";
  inner += _renderHeader(payload);
  inner += _renderAdvisory(advisory ?? null);
  inner += _renderCompletenessPanel(payload.completenessFinding);
  if (sections.length === 0) {
    inner +=
      '<div class="leo-empty" data-testid="leo-empty">' +
      "No SBAR content yet.</div>";
  } else {
    inner += sections.map((s) => _renderStage(s, partsByStage)).join("");
  }
  inner += _renderGuidelineMatches(payload.guidelineMatches);

  const wrapper =
    (root as Element).querySelector?.(".leo-root") ?? null;
  let host: Element;
  if (wrapper) {
    host = wrapper;
  } else {
    const div = (root.ownerDocument ?? document).createElement("div");
    div.className = "leo-root";
    div.setAttribute("data-testid", "leo-root");
    div.setAttribute("data-assessment-id", payload.assessmentId);
    (root as ParentNode).appendChild(div);
    host = div;
  }
  host.innerHTML = inner;

  const teardown = attachDisclosureHandlers(host, {
    onOpen: ({ stage }) =>
      emit({
        type: LEO_EVENT_NAMES.disclosureOpened,
        detail: { assessmentId: payload.assessmentId, stage },
      }),
    onClose: ({ stage }) =>
      emit({
        type: LEO_EVENT_NAMES.disclosureClosed,
        detail: { assessmentId: payload.assessmentId, stage },
      }),
    onSourceClicked: ({ stage, sourceId }) =>
      emit({
        type: LEO_EVENT_NAMES.sourceClicked,
        detail: { assessmentId: payload.assessmentId, stage, sourceId },
      }),
  });

  emit({
    type: LEO_EVENT_NAMES.loaded,
    detail: { assessmentId: payload.assessmentId },
  });

  return teardown;
}
