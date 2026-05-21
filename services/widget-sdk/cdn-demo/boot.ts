/**
 * CDN integrator demo boot script.
 *
 * Configures the synthetic demo fetcher before registering the custom
 * element so the in-page <leo-sbar> loads stub data from the CDN origin.
 */

import { configureDemoFetcher } from "../src/demo/fixture";
import { registerLeoSbarElement } from "../src/component";
import { LEO_EVENT_NAMES } from "../src/data/types";

configureDemoFetcher("ass-2WW-demo");
registerLeoSbarElement();

function wireWebComponentStatus(): void {
  const widget = document.getElementById("leo-widget");
  const status = document.getElementById("wc-status");
  if (!widget || !status) return;

  widget.addEventListener(LEO_EVENT_NAMES.loaded, () => {
    status.textContent = "Web component loaded (leo:loaded).";
  });
  widget.addEventListener(LEO_EVENT_NAMES.error, (event) => {
    const detail = (event as CustomEvent).detail as { errorMessage?: string };
    status.textContent =
      "Web component error: " + (detail.errorMessage ?? "unknown");
  });
}

function wireIframeStatus(): void {
  const status = document.getElementById("iframe-status");
  if (!status) return;

  window.addEventListener("message", (event) => {
    const data = event.data as {
      source?: string;
      type?: string;
      detail?: { errorMessage?: string };
    };
    if (data?.source !== "leo-widget" || !data.type) return;
    if (data.type === LEO_EVENT_NAMES.loaded) {
      status.textContent = "Iframe variant loaded (leo:loaded via postMessage).";
    }
    if (data.type === LEO_EVENT_NAMES.error) {
      status.textContent =
        "Iframe variant error: " + (data.detail?.errorMessage ?? "unknown");
    }
  });
}

wireWebComponentStatus();
wireIframeStatus();
