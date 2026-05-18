/**
 * @mizaic/leo-widget public entry.
 *
 * Importing this module registers the <leo-sbar> custom element and
 * re-exports the public type contracts.
 *
 * Atlas trace:
 *   DI: DI-85C95E53 (the same source tree publishes the NPM package
 *       and the CDN bundle at /v1/leo-widget.js)
 *   DI: DI-A1206416 (re-exports configureFetcher seam for hosts that
 *       want to override the proxy transport during local dev)
 */

import { registerLeoSbarElement } from "./component";

registerLeoSbarElement();

export { LeoSbarElement, registerLeoSbarElement } from "./component";
export type {
  SbarAssessmentPayload,
  SbarBackgroundPart,
  SbarSection,
  SbarStageName,
  LeoEventName,
  LeoEventPayload,
} from "./data/types";
export { LEO_EVENT_NAMES } from "./data/types";
export {
  configureFetcher,
  fetchAssessment,
  type FetchAssessmentArgs,
  type FetchAssessmentFn,
} from "./data/fetcher";
