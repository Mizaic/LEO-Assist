/**
 * VT-LEO-AI-194 -- useSbarStream wire-format contract
 *
 * Pins the UI -> backend type translation between the snake_case
 * identifiers we use in TypeScript and the PascalCase node labels that
 * libs/sbar/events.SituationArtifactType / BackgroundSourceType serialise
 * as. Drift between these two sides produced a 422 enum error in the
 * playground (R-LEO-AI-185 -- failure to start the SBAR job means the
 * reviewer falls back to ad-hoc summarisation).
 *
 * The mapping is asserted two ways:
 *   1. statically against the TypeScript source, so the dictionary is
 *      always up to date with the union types,
 *   2. dynamically by capturing the JSON body sent to /api/sbar/jobs.
 */
import fs from "fs";
import path from "path";
import { act, renderHook } from "@testing-library/react";

import { useSbarStream } from "../hooks/useSbarStream";

const HOOK_PATH = path.resolve(__dirname, "..", "hooks", "useSbarStream.ts");

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("useSbarStream wire-format mapping", () => {
  it("declares the artefact and background mappers", () => {
    const src = read(HOOK_PATH);
    expect(src).toMatch(/ARTIFACT_TYPE_WIRE/);
    expect(src).toMatch(/BACKGROUND_TYPE_WIRE/);
    expect(src).toMatch(/patient_context:\s*"PatientContext"/);
    expect(src).toMatch(/referral_request:\s*"ReferralRequest"/);
    expect(src).toMatch(/procedure_request:\s*"ProcedureRequest"/);
    expect(src).toMatch(/summarisation_context:\s*"SummarisationContext"/);
    expect(src).toMatch(/fixed_text:\s*"FixedText"/);
    expect(src).toMatch(/encounter:\s*"Encounter"/);
    expect(src).toMatch(/document_reference:\s*"DocumentReference"/);
    expect(src).toMatch(/chunk:\s*"Chunk"/);
  });

  it("posts PascalCase artefact and background types", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: "run-1", assessment_id: "asm-1" }),
      text: async () => "",
    });
    const realFetch = global.fetch;
    (global as any).fetch = fetchMock;
    // jsdom does not implement EventSource. Provide a no-op stand-in
    // so the SSE subscribe step does not throw -- this test only cares
    // about the POST body.
    class FakeES {
      onerror: (() => void) | null = null;
      addEventListener() {}
      close() {}
    }
    const realES = (global as any).EventSource;
    (global as any).EventSource = FakeES;
    try {
      const { result } = renderHook(() => useSbarStream());
      await act(async () => {
        await result.current.start({
          patientId: "patient-1",
          artifacts: [
            { type: "patient_context", id: "patient-1" },
            {
              type: "summarisation_context",
              context_value: "clinic_review_letter",
            },
          ],
          background: [
            { type: "encounter", id: "enc-1" },
            { type: "document_reference", id: "doc-1" },
            { type: "chunk", id: "chunk-1" },
          ],
          guidelineIds: ["nice-ng28"],
          concern: "Borderline foot pulses",
        });
      });
      // close the EventSource that subscribe() opened so jest can exit.
      act(() => {
        result.current.cancel();
      });

      expect(fetchMock).toHaveBeenCalled();
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("/api/sbar/jobs");
      const body = JSON.parse(init.body as string);
      expect(body.situation.artifacts).toEqual([
        { type: "PatientContext", id: "patient-1" },
        {
          type: "SummarisationContext",
          context_value: "clinic_review_letter",
        },
      ]);
      expect(body.background).toEqual([
        { type: "Encounter", id: "enc-1" },
        { type: "DocumentReference", id: "doc-1" },
        { type: "Chunk", id: "chunk-1" },
      ]);
      expect(body.concern).toBe("Borderline foot pulses");
    } finally {
      (global as any).fetch = realFetch;
      (global as any).EventSource = realES;
    }
  });
});
