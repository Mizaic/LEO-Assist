/**
 * <leo-sbar> custom element with a closed shadow root.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (closed shadow root is the trust boundary that
 *       isolates the source-record disclosure from host CSS / JS)
 *   DI: DI-85944331 (locked branding compiled into the shadow CSS)
 *   DI: DI-A1206416 (token + proxy-origin attributes wire the
 *       host-proxied auth flow)
 *   Risk mitigated: R-4965BCD2
 *
 * The shadow root is opened in CLOSED mode. The element does not
 * expose `shadowRoot` to host JS; we keep our own private reference.
 * That is the strictest browser-enforced isolation available for a
 * web component and is the AC for "host JS attempting to query or
 * mutate widget-internal DOM is rejected by browser sandboxing"
 * (DI-85C95E53 acceptance criterion 3).
 */

import { LEO_EVENT_NAMES } from "./data/types";
import type { SbarAssessmentPayload } from "./data/types";
import { fetchAssessment, fetchSourceText } from "./data/fetcher";
import { buildShadowStylesheet } from "./branding/stylesheet";
import { renderSurface } from "./sbar/surface";

const ELEMENT_NAME = "leo-sbar";

const _shadowRoots = new WeakMap<LeoSbarElement, ShadowRoot>();
const _teardowns = new WeakMap<LeoSbarElement, () => void>();

export class LeoSbarElement extends HTMLElement {
  static readonly observedAttributes = [
    "assessment-id",
    "widget-token",
    "proxy-origin",
    "advisory",
  ] as const;

  constructor() {
    super();
    const shadow = this.attachShadow({ mode: "closed" });
    _shadowRoots.set(this, shadow);
    const style = document.createElement("style");
    style.textContent = buildShadowStylesheet();
    shadow.appendChild(style);
  }

  connectedCallback(): void {
    void this._refresh();
  }

  disconnectedCallback(): void {
    const teardown = _teardowns.get(this);
    if (teardown) teardown();
    _teardowns.delete(this);
  }

  attributeChangedCallback(): void {
    if (this.isConnected) void this._refresh();
  }

  private _emit(event: {
    type: string;
    detail: Record<string, unknown>;
  }): void {
    this.dispatchEvent(
      new CustomEvent(event.type, {
        detail: event.detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private async _refresh(): Promise<void> {
    const shadow = _shadowRoots.get(this);
    if (!shadow) return;
    const assessmentId = this.getAttribute("assessment-id") ?? "";
    const widgetToken = this.getAttribute("widget-token") ?? "";
    const proxyOrigin =
      this.getAttribute("proxy-origin") ?? window.location.origin;
    const advisory = this.getAttribute("advisory");
    if (!assessmentId || !widgetToken) {
      this._renderError(
        "Missing required attributes: assessment-id, widget-token.",
      );
      return;
    }
    try {
      const payload = await fetchAssessment({
        assessmentId,
        widgetToken,
        proxyOrigin,
      });
      const teardown = renderSurface(shadow, {
        payload,
        advisory,
        emit: (e) =>
          this._emit({ type: e.type, detail: e.detail as Record<string, unknown> }),
        resolveSourceText: (sourceId) =>
          fetchSourceText({ assessmentId, sourceId, widgetToken, proxyOrigin })
            .then((result) => result.text || null)
            .catch(() => null),
      });
      const previous = _teardowns.get(this);
      if (previous) previous();
      _teardowns.set(this, teardown);
      this.setAttribute("data-leo-state", "loaded");
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      this._renderError(message);
      this._emit({
        type: LEO_EVENT_NAMES.error,
        detail: { assessmentId, errorMessage: message },
      });
    }
  }

  private _renderError(message: string): void {
    const shadow = _shadowRoots.get(this);
    if (!shadow) return;
    let root = shadow.querySelector(".leo-root");
    if (!root) {
      root = document.createElement("div");
      root.className = "leo-root";
      shadow.appendChild(root);
    }
    root.innerHTML =
      '<div class="leo-error" role="alert" data-testid="leo-error">' +
      message
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;") +
      "</div>";
  }
}

export function registerLeoSbarElement(): void {
  if (typeof customElements === "undefined") return;
  if (!customElements.get(ELEMENT_NAME)) {
    customElements.define(ELEMENT_NAME, LeoSbarElement);
  }
}

/** Test-only seam: read the closed shadow root from inside the SDK. */
export function _readShadowRootForTesting(
  element: LeoSbarElement,
): ShadowRoot | undefined {
  return _shadowRoots.get(element);
}

/** Test-only seam: pre-render an SBAR payload without fetching. */
export function _renderForTesting(
  element: LeoSbarElement,
  payload: SbarAssessmentPayload,
  advisory: string | null = null,
): void {
  const shadow = _shadowRoots.get(element);
  if (!shadow) return;
  const teardown = renderSurface(shadow, {
    payload,
    advisory,
    emit: (e) =>
      element.dispatchEvent(
        new CustomEvent(e.type, {
          detail: e.detail,
          bubbles: true,
          composed: true,
        }),
      ),
  });
  const previous = _teardowns.get(element);
  if (previous) previous();
  _teardowns.set(element, teardown);
}
