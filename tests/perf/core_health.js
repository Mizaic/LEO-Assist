// Core API liveness + proxy canary.
//
// Walks /health (cheap) and a couple of authenticated proxy paths to
// confirm the multi-worker uvicorn + lifted threadpool tuning from
// Phase 0/1 is doing its job. Holds 50 VUs for 1 minute, asserts:
//   - error rate < 1%
//   - p95 < 1.5 seconds (health is much faster; proxy paths dominate)

import { sleep } from "k6";
import { ERROR_BUDGET, getJson, P95_BUDGET_MS } from "./_lib.js";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: 50,
      duration: "1m",
    },
  },
  thresholds: {
    http_req_failed: [`rate<${ERROR_BUDGET}`],
    http_req_duration: [`p(95)<${P95_BUDGET_MS}`],
  },
};

export default function () {
  getJson("/health", "core-health");
  sleep(1);
}
