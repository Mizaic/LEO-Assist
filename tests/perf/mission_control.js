// Mission Control list/KPI canary.
//
// Mirrors the dashboard load pattern: pull patients + KPIs + an
// encounters page in quick succession. Asserts the de-asynced
// FastAPI handlers (def vs async def + threadpool) keep up with
// 30 VUs for 1 minute.

import { sleep } from "k6";
import { ERROR_BUDGET, getJson, P95_BUDGET_MS } from "./_lib.js";

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: 30,
      duration: "1m",
    },
  },
  thresholds: {
    http_req_failed: [`rate<${ERROR_BUDGET}`],
    http_req_duration: [`p(95)<${P95_BUDGET_MS + 500}`],
  },
};

export default function () {
  getJson("/analytics/mission-control/kpis", "mc-kpis");
  getJson(
    "/analytics/mission-control/patients?page=1&page_size=20",
    "mc-patients",
  );
  getJson(
    "/analytics/mission-control/encounters?page=1&page_size=20",
    "mc-encounters",
  );
  sleep(2);
}
