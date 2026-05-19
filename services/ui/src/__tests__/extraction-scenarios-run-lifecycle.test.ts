/**
 * VT-C0D7D50C -- Extraction validation run lifecycle and Neo4j persistence.
 *
 * Static-source verification that the UI-triggered validation run backend
 * tracks queued/running/completed/failed states and persists F1 results to
 * Neo4j (DI-B492CAFD AC2 and AC3).
 *
 * Atlas:
 *   DI: DI-B492CAFD
 *   DO: DO-416BA91D
 *   VT: VT-C0D7D50C
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function src(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const ROUTER = "services/api/app/routers/extraction_scenarios.py";
const CYPHER = "libs/cypher/extraction_scenario_queries.py";

describe("VT-C0D7D50C - Extraction validation run lifecycle and Neo4j persistence", () => {
  test("TC-001: POST /runs returns queued status and starts a background thread", () => {
    const router = src(ROUTER);
    expect(router).toMatch(/@router\.post\("\/runs"\)/);
    expect(router).toMatch(/"status":\s*"queued"/);
    expect(router).toMatch(/threading\.Thread/);
    expect(router).toMatch(/target=_execute_run/);
  });

  test("TC-002: worker transitions running, completed, and failed states", () => {
    const router = src(ROUTER);
    expect(router).toMatch(/_set_run\(run_id,\s*\{"status":\s*"running"/);
    expect(router).toMatch(/"status":\s*"failed"/);
    expect(router).toMatch(/"status":\s*"completed"/);
    expect(router).toMatch(/GET_VALIDATION_RUN/);
  });

  test("TC-003: CREATE_VALIDATION_RUN MERGEs ExtractionValidationRun in Neo4j", () => {
    const cypher = src(CYPHER);
    expect(cypher).toMatch(/CREATE_VALIDATION_RUN\s*=/);
    expect(cypher).toMatch(/MERGE \(r:ExtractionValidationRun \{run_id: \$run_id\}\)/);
    expect(cypher).toMatch(/r\.status\s+= \$status/);
    expect(cypher).toMatch(/r\.pass_threshold\s+= \$pass_threshold/);
  });

  test("TC-004: COMPLETE_VALIDATION_RUN stores F1, pass/fail, and per-case results", () => {
    const cypher = src(CYPHER);
    expect(cypher).toMatch(/COMPLETE_VALIDATION_RUN\s*=/);
    expect(cypher).toMatch(/r\.overall_f1\s+= \$overall_f1/);
    expect(cypher).toMatch(/r\.overall_precision\s+= \$overall_precision/);
    expect(cypher).toMatch(/r\.overall_recall\s+= \$overall_recall/);
    expect(cypher).toMatch(/r\.passed\s+= \$passed/);
    expect(cypher).toMatch(/r\.per_case_results\s+= \$per_case_results/);
  });

  test("TC-005: finalise run writes COMPLETE_VALIDATION_RUN from the router", () => {
    const router = src(ROUTER);
    expect(router).toMatch(/COMPLETE_VALIDATION_RUN/);
    expect(router).toMatch(/overall_f1=f1/);
    expect(router).toMatch(/overall_precision=precision/);
    expect(router).toMatch(/overall_recall=recall/);
    expect(router).toMatch(/passed=passed/);
    expect(router).toMatch(/per_case_results=json\.dumps\(per_case\)/);
  });
});
