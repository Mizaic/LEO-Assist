/**
 * Static-source VT for the Mission Control reconcile + lock API client.
 *
 * Atlas trace:
 *   DO: services/ui/src/lib/missionControlApi.ts (reconcile additions)
 *   DI: DI-9DCC9F84 (Reconcile pathway)
 *   DI: DI-C424BB44 (VerificationLock primitive)
 *   VT: this file
 *
 * Why static-source rather than live-render: this module is the
 * network shim. Anything that hits fetch on import will fail under
 * jsdom; instead we inspect the source string and assert structural
 * invariants that the drawer + e2e tests rely on.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const SOURCE = fs.readFileSync(
  path.join(ROOT, "services/ui/src/lib/missionControlApi.ts"),
  "utf8"
);

describe("missionControlApi -- reconcile + lock client", () => {
  test("exports the reconcile and lock surface the drawer needs", () => {
    expect(SOURCE).toMatch(/export\s+(?:async\s+)?function\s+patchEpisodeReconcile/);
    expect(SOURCE).toMatch(/export\s+(?:async\s+)?function\s+listLocksForEpisode/);
    expect(SOURCE).toMatch(/export\s+(?:async\s+)?function\s+lockEntity/);
    expect(SOURCE).toMatch(/export\s+(?:async\s+)?function\s+unlockEntity/);
  });

  test("declares the shared types so callers cannot drift", () => {
    expect(SOURCE).toContain("ReconcileActionType");
    expect(SOURCE).toContain("ReconcileAction");
    expect(SOURCE).toContain("ReconcileRequestBody");
    expect(SOURCE).toContain("ReconcileResponse");
    expect(SOURCE).toContain("VerificationLockSummary");
    expect(SOURCE).toContain("EpisodeLocksResponse");
    expect(SOURCE).toContain("LockEntityType");
    expect(SOURCE).toContain("ReviewerRole");
  });

  test("ReconcileActionType matches the server enum 1-for-1", () => {
    const block = sliceTypeAlias(SOURCE, "ReconcileActionType");
    expect(block).toContain('"confirm"');
    expect(block).toContain('"replace"');
    expect(block).toContain('"detach"');
    expect(block).toContain('"not_applicable"');
  });

  test("ReviewerRole matches the server enum 1-for-1", () => {
    const block = sliceTypeAlias(SOURCE, "ReviewerRole");
    expect(block).toContain('"clinician"');
    expect(block).toContain('"qa_ra_lead"');
  });

  test("LockEntityType covers every lockable entity in libs/locks/models.py", () => {
    for (const t of [
      "episode",
      "encounter",
      "is_part_of_edge",
      "coded_link",
      "assertion",
    ]) {
      expect(SOURCE).toContain(`"${t}"`);
    }
  });

  test("patchEpisodeReconcile uses PATCH on the analytics proxy path", () => {
    const fn = extractFunctionBody(SOURCE, "patchEpisodeReconcile");
    expect(fn).toContain("/mission-control/episodes/");
    expect(fn).toContain("/reconcile");
    expect(fn).toContain('method: "PATCH"');
    expect(fn).toContain("encodeURIComponent(episodeId)");
    expect(fn).toContain("PROXY");
  });

  test("listLocksForEpisode uses GET on the analytics proxy path", () => {
    const fn = extractFunctionBody(SOURCE, "listLocksForEpisode");
    expect(fn).toContain("/mission-control/episodes/");
    expect(fn).toContain("/locks");
    expect(fn).toContain("encodeURIComponent(episodeId)");
    expect(fn).not.toContain('method:');
  });

  test("lockEntity hard-codes accept and uses the patient lock endpoint", () => {
    const fn = extractFunctionBody(SOURCE, "lockEntity");
    expect(fn).toContain("/api/patients/");
    expect(fn).toContain("/coded-links/");
    expect(fn).toContain("/lock");
    expect(fn).toContain('method: "POST"');
    expect(fn).toContain('decision: "accept"');
  });

  test("unlockEntity hard-codes reject and uses the same endpoint", () => {
    const fn = extractFunctionBody(SOURCE, "unlockEntity");
    expect(fn).toContain("/api/patients/");
    expect(fn).toContain("/coded-links/");
    expect(fn).toContain("/lock");
    expect(fn).toContain('method: "POST"');
    expect(fn).toContain('decision: "reject"');
  });

  test("the new helpers go through fetchJson so 401 -> reauth", () => {
    for (const name of [
      "patchEpisodeReconcile",
      "listLocksForEpisode",
      "lockEntity",
      "unlockEntity",
    ]) {
      const body = extractFunctionBody(SOURCE, name);
      expect(body).toContain("fetchJson");
    }
  });

  test("Atlas trace header for the reconcile section is present", () => {
    expect(SOURCE).toContain("DI-C424BB44");
    expect(SOURCE).toContain("DI-9DCC9F84");
  });
});

/** Extract the body of `export type Name = ... ;` so the test can
 * assert on each member without writing a multiline regex. */
function sliceTypeAlias(source: string, name: string): string {
  const re = new RegExp(`export\\s+type\\s+${name}\\b[^=]*=`);
  const m = re.exec(source);
  if (!m) throw new Error(`type ${name} not found`);
  const start = m.index + m[0].length;
  const end = source.indexOf(";", start);
  if (end < 0) throw new Error(`type ${name} has no terminator`);
  return source.slice(start, end);
}

/** Extract the raw text of an exported async function so individual
 * assertions can target only that function and not other helpers. */
function extractFunctionBody(source: string, name: string): string {
  const re = new RegExp(
    `export\\s+(?:async\\s+)?function\\s+${name}\\b[^{]*\\{`,
    "m"
  );
  const match = re.exec(source);
  if (!match) {
    throw new Error(`function ${name} not found in source`);
  }
  let depth = 1;
  let i = match.index + match[0].length;
  while (i < source.length && depth > 0) {
    const ch = source[i];
    if (ch === "{") depth += 1;
    else if (ch === "}") depth -= 1;
    i += 1;
  }
  return source.slice(match.index, i);
}
