// Shared helpers for the k6 perf canaries.
//
// These are deliberately small. We do not want a 500-line k6 framework;
// each canary should be readable in 30 seconds. Anything reused across
// scripts lives here.

import http from "k6/http";
import { check } from "k6";

export const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
export const SESSION_COOKIE = __ENV.SESSION_COOKIE || "";
export const P95_BUDGET_MS = Number(__ENV.P95_BUDGET_MS || "2000");
export const ERROR_BUDGET = Number(__ENV.ERROR_BUDGET || "0.01");

export function authHeaders(extra) {
  const headers = {
    "X-Requested-With": "XMLHttpRequest",
    Accept: "application/json",
    ...(extra || {}),
  };
  if (SESSION_COOKIE) {
    headers["Cookie"] = SESSION_COOKIE;
  }
  return headers;
}

export function getJson(path, name) {
  const res = http.get(`${BASE_URL}${path}`, {
    headers: authHeaders(),
    tags: { name: name || path },
  });
  check(res, {
    "status is 2xx": (r) => r.status >= 200 && r.status < 300,
  });
  return res;
}

export function postJson(path, body, name) {
  const res = http.post(
    `${BASE_URL}${path}`,
    JSON.stringify(body || {}),
    {
      headers: authHeaders({ "Content-Type": "application/json" }),
      tags: { name: name || path },
    },
  );
  check(res, {
    "status is 2xx": (r) => r.status >= 200 && r.status < 300,
  });
  return res;
}
