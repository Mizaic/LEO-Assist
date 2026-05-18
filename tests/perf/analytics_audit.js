// Analytics API audit dashboard canary.
//
// Drives the same fan-out the /audit page issues from the browser
// (12 parallel calls) so any regression in _run_multi_scope or in
// the singleton Neo4j driver shows up immediately. Holds 25 VUs for
// 1 minute, asserts:
//   - error rate < 1%
//   - p95 < 2 seconds per audit endpoint

import { sleep } from "k6";
import {
  ERROR_BUDGET,
  getJson,
  P95_BUDGET_MS,
} from "./_lib.js";

const AUDIT_PATHS = [
  "/analytics/audit/summary",
  "/analytics/audit/cancer-type",
  "/analytics/audit/cancer-stage",
  "/analytics/audit/demographics",
  "/analytics/audit/comorbidities",
  "/analytics/audit/place-of-presentation",
  "/analytics/audit/consultations",
  "/analytics/audit/investigations",
  "/analytics/audit/referrals",
  "/analytics/audit/intervals",
  "/analytics/audit/safety-netting",
  "/analytics/audit/avoidable-delays",
];

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: 25,
      duration: "1m",
    },
  },
  thresholds: {
    http_req_failed: [`rate<${ERROR_BUDGET}`],
    http_req_duration: [`p(95)<${P95_BUDGET_MS}`],
  },
};

export default function () {
  for (const path of AUDIT_PATHS) {
    getJson(path, path);
  }
  sleep(2);
}
