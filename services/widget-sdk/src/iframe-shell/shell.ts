/**
 * Hardened iframe variant entry.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (iframe is the second variant of the same source
 *       tree; the cross-origin frame is the trust boundary)
 *   DI: DI-85944331 (locked branding inlined into the iframe document)
 *   DI: DI-A1206416 (the iframe receives token + assessment via URL
 *       params and proxies through host-controlled origin)
 *
 * The iframe is served from the LEO-controlled origin pinned by the
 * `WIDGET_PUBLIC_HOST` env var at deploy time (e.g.
 * https://leoaiwidgetcdnprod.z33.web.core.windows.net). Same-origin
 * policy keeps host JS and host CSS out of this document. Lifecycle
 * events are posted back to window.parent via postMessage; the host
 * listens for them. This script reads ALL configurable URLs from
 * URL params (assessment-id, widget-token, proxy-origin, advisory)
 * so the same shell.js bundle works regardless of which CDN host
 * serves it.
 */

import { LEO_EVENT_NAMES } from "../data/types";
import type { SbarAssessmentPayload } from "../data/types";
import { fetchAssessment } from "../data/fetcher";
import { configureDemoFetcher } from "../demo/fixture";
import { buildShadowStylesheet } from "../branding/stylesheet";
import { renderSurface } from "../sbar/surface";

const PARAMS = new URLSearchParams(window.location.search);
const ASSESSMENT_ID = PARAMS.get("assessment-id") ?? "";
const WIDGET_TOKEN = PARAMS.get("widget-token") ?? "";
const PROXY_ORIGIN = PARAMS.get("proxy-origin") ?? window.location.origin;
const ADVISORY = PARAMS.get("advisory");

if (PARAMS.get("demo") === "1") {
  configureDemoFetcher(ASSESSMENT_ID || undefined);
}

function _ensureBaseStyles(): void {
  const existing = document.head.querySelector("style[data-leo='shell']");
  if (existing) return;
  const style = document.createElement("style");
  style.setAttribute("data-leo", "shell");
  // The :host rule from the shadow stylesheet does not apply here;
  // map it onto the body inside the iframe document instead.
  style.textContent = buildShadowStylesheet().replace(/:host/g, "body");
  document.head.appendChild(style);
}

function _emit(event: { type: string; detail: Record<string, unknown> }): void {
  const message = { source: "leo-widget", type: event.type, detail: event.detail };
  try {
    window.parent.postMessage(message, "*");
  } catch {
    // postMessage to a cross-origin parent never throws under normal
    // conditions; swallow defensively for sandboxed iframes that
    // disable scripts in the parent.
  }
}

function _renderError(message: string): void {
  const mount = document.getElementById("leo-iframe-mount");
  if (!mount) return;
  mount.innerHTML =
    '<div class="leo-root" data-testid="leo-root">' +
    '<div class="leo-error" role="alert" data-testid="leo-error">' +
    message
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;") +
    "</div></div>";
}

async function _boot(): Promise<void> {
  _ensureBaseStyles();
  if (!ASSESSMENT_ID || !WIDGET_TOKEN) {
    _renderError("Missing required URL params: assessment-id, widget-token.");
    return;
  }
  const mount = document.getElementById("leo-iframe-mount");
  if (!mount) return;
  let payload: SbarAssessmentPayload;
  try {
    payload = await fetchAssessment({
      assessmentId: ASSESSMENT_ID,
      widgetToken: WIDGET_TOKEN,
      proxyOrigin: PROXY_ORIGIN,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    _renderError(message);
    _emit({
      type: LEO_EVENT_NAMES.error,
      detail: { assessmentId: ASSESSMENT_ID, errorMessage: message },
    });
    return;
  }
  renderSurface(mount, {
    payload,
    advisory: ADVISORY,
    emit: (e) => _emit(e),
  });
}

void _boot();

/** Test seam: render a known payload without fetching. */
export function _renderForTesting(
  payload: SbarAssessmentPayload,
  advisory: string | null = null,
): void {
  _ensureBaseStyles();
  const mount = document.getElementById("leo-iframe-mount");
  if (!mount) return;
  renderSurface(mount, { payload, advisory, emit: (e) => _emit(e) });
}
