/**
 * Routes for the Add form template skip-box journey.
 *
 * Detect and save go through the real form-schema router, run by
 * form_schema_router_bridge.py. Only the large language model detector
 * and the graph are replaced there. Sign-in, organisations, the
 * fingerprint and the template library are stubbed here.
 *
 * Atlas trace: UN-AF530E8E -> DI-455C4EF1 -> DO-B7A3AF41 -> VT-8E71E0F1
 */
import { execFileSync } from "child_process";
import fs from "fs";
import path from "path";
import type { Page, Route } from "@playwright/test";

import { fulfillJson, stubKnowledgeAdminAuth } from "./surface-forms-fixtures";

const REPO_ROOT = path.resolve(__dirname, "../../../..");
const BRIDGE = path.join(__dirname, "form_schema_router_bridge.py");
const PYTHON =
  process.platform === "win32"
    ? path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
    : path.join(REPO_ROOT, ".venv", "bin", "python");

export const SKIP_BOX_FINGERPRINT = "fp-sfh-lower-gi-val";
export const SKIP_BOX_FORM_NAME = "Sherwood Lower GI 2WW";
export const HOSPITAL_BOXES = [
  "Pt Contacted",
  "Interpreter Booked",
  "Transport Booked",
  "Accepted",
];
export const LOWER_GI_LETTER = fs.readFileSync(
  path.join(REPO_ROOT, "tests", "fixtures", "form_schema", "sfh_lower_gi_2ww_deid.md"),
  "utf8",
);

function section(id: string, type: string, label: string, items: string[] = []) {
  return {
    section_id: id,
    section_type: type,
    label,
    start_pattern: label,
    items: items.map((p) => ({ pattern: p, entity_text: p })),
  };
}

/** What the model gives for this letter: admin sections are heading only. */
const MODEL_SECTIONS = [
  section("S1", "admin", "SECTION 1 - PATIENT DEMOGRAPHIC DETAILS"),
  section("S2", "checkbox_multi", "SECTION 2: Symptoms suggesting colorectal cancer", [
    "Change in bowel habit",
    "New onset of abdominal pain",
    "Definite palpable abdominal mass",
    "Unexplained iron deficiency anaemia",
    "New onset of constipation",
    "New onset of Diarrhoea",
    "Significant unexplained weight loss",
    "Rectal mass",
    "Unexplained rectal bleeding",
  ]),
  section("S3", "scale", "Performance Status - Clinical Frailty Scale", [
    "Very Fit",
    "Managing well",
    "Very Mild",
    "Mild",
    "Moderate",
    "Severe",
    "Very severe",
    "Terminally ill",
  ]),
  section("S4", "free_text", "SECTION 3 - PAST MEDICAL HISTORY"),
  section("S5", "admin", "Hospital Use Only"),
];

interface RouterReply {
  status: number;
  body: unknown;
}

function callRouter(method: string, apiPath: string, body: unknown): RouterReply {
  const out = execFileSync(PYTHON, [BRIDGE], {
    cwd: REPO_ROOT,
    input: JSON.stringify({ method, path: apiPath, body, detected: MODEL_SECTIONS }),
    encoding: "utf8",
    maxBuffer: 16 * 1024 * 1024,
    env: { ...process.env, PYTHONIOENCODING: "utf-8" },
  });
  const lines = out.trim().split(/\r?\n/);
  return JSON.parse(lines[lines.length - 1]) as RouterReply;
}

async function forward(route: Route, method: string, apiPath: string): Promise<RouterReply> {
  const reply = callRouter(method, apiPath, route.request().postDataJSON());
  await fulfillJson(route, reply.body, reply.status);
  return reply;
}

/** Saves the real router accepted, newest last. */
export interface SaveLog {
  accepted: Array<{
    fingerprint: string;
    form_name: string;
    sections: unknown[];
    saved_at?: string;
  }>;
  refused: string[];
}

async function handleFormSchemas(route: Route, log: SaveLog): Promise<void> {
  const req = route.request();
  const { pathname } = new URL(req.url());
  const apiPath = pathname.replace(/^\/api/, "");
  if (req.method() === "POST" && apiPath === "/form-schemas/fingerprint") {
    return fulfillJson(route, { fingerprint: SKIP_BOX_FINGERPRINT });
  }
  if (req.method() === "POST" && apiPath === "/form-schemas/detect") {
    await forward(route, "POST", apiPath);
    return;
  }
  if (req.method() === "PUT") {
    const reply = await forward(route, "PUT", apiPath);
    recordSave(reply, log);
    return;
  }
  if (apiPath === "/form-schemas") {
    return fulfillJson(route, { schemas: log.accepted.map(summary) });
  }
  return fulfillJson(route, { schema: null, match: "none", schemas: [] });
}

function recordSave(reply: RouterReply, log: SaveLog): void {
  const body = reply.body as { schema?: SaveLog["accepted"][number]; detail?: string };
  if (reply.status === 200 && body.schema) {
    log.accepted.push({ ...body.schema, saved_at: new Date().toISOString() });
  } else {
    log.refused.push(String(body.detail ?? reply.status));
  }
}

function summary(schema: SaveLog["accepted"][number]) {
  return {
    schema_id: "val-" + schema.fingerprint,
    fingerprint: schema.fingerprint,
    form_name: schema.form_name,
    status: "active",
    created_at: schema.saved_at,
    updated_at: schema.saved_at,
    organization_id: "",
    service_id: "",
  };
}

export async function stubAddTemplateRoutes(page: Page): Promise<SaveLog> {
  const log: SaveLog = { accepted: [], refused: [] };
  await stubKnowledgeAdminAuth(page);
  await page.route("**/api/admin/orgs", (route) =>
    fulfillJson(route, [{ id: "RK5", name: "Sherwood Forest Hospitals" }]),
  );
  await page.route("**/api/admin/orgs/*/services", (route) =>
    fulfillJson(route, [{ id: "svc-lower-gi", name: "Lower GI 2WW" }]),
  );
  await page.route("**/api/form-schemas**", (route) => handleFormSchemas(route, log));
  return log;
}
