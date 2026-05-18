/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

/**
 * Status banners shown above the ProbeMonitor body when the
 * source step never executed, was halted, or sat outside the partial
 * run boundary (Phase 6b-vi decomposition).
 *
 * Each banner is presentational only and isolated so the parent
 * monitor stays small and readable.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

interface SourceTraceLike {
  halt_reason?: string;
}

const BANNER_BASE = {
  borderBottom: "1px solid #313244",
  padding: "10px 12px",
} as const;

export function HaltedBanner({ sourceTrace }: { sourceTrace: SourceTraceLike | null }) {
  return (
    <div style={{ ...BANNER_BASE, background: "#2d1b1b", borderBottom: "1px solid #f38ba840" }}>
      <div style={{ color: "#f38ba8", fontWeight: 700, fontSize: 11, marginBottom: 6 }}>
        🛑 Pipeline stopped here
      </div>
      <div style={{ color: "#cdd6f4", fontSize: 10, lineHeight: 1.5 }}>
        This step ran but the quality gate decided the results weren&apos;t good enough
        to continue. Check the probe details above to see what failed, then fix the
        issue and run again.
      </div>
      {sourceTrace?.halt_reason === "verification_failed" && (
        <div style={{ color: "#fab387", fontSize: 10, marginTop: 6 }}>
          Verification found issues with the extracted entities. Downstream steps
          (terminology coding, saving, etc.) were not run.
        </div>
      )}
    </div>
  );
}

export function PartialRunEndBanner() {
  return (
    <div style={{ ...BANNER_BASE, background: "#1a2a1a", borderBottom: "1px solid #a6e3a140" }}>
      <div style={{ color: "#a6e3a1", fontWeight: 700, fontSize: 11, marginBottom: 4 }}>
        ▶ Partial run stopped here
      </div>
      <div style={{ color: "#a6adc8", fontSize: 10, lineHeight: 1.5 }}>
        This is as far as the last &quot;Run to here&quot; went. Steps to the right
        were not run. Click <span style={{ color: "#89b4fa" }}>Run all steps</span> to
        execute the full pipeline.
      </div>
    </div>
  );
}

export function NotReachedBanner() {
  return (
    <div style={{ background: "#1a1a2e", padding: "14px 12px", borderBottom: "1px solid #313244" }}>
      <div style={{ color: "#6c7086", fontWeight: 700, fontSize: 11, marginBottom: 6 }}>
        ⏹ Pipeline stopped before reaching this step
      </div>
      <div style={{ color: "#45475a", fontSize: 10, lineHeight: 1.5 }}>
        A quality gate earlier in the pipeline halted the run. This step never
        executed. Fix the problem on the node marked 🛑 red and run again.
      </div>
    </div>
  );
}

export function NotReachedByPartialRunBanner() {
  return (
    <div style={{ background: "#1a1a2e", padding: "14px 12px", borderBottom: "1px solid #313244" }}>
      <div style={{ color: "#6c7086", fontWeight: 700, fontSize: 11, marginBottom: 6 }}>
        ⏹ Not run — beyond the partial run boundary
      </div>
      <div style={{ color: "#45475a", fontSize: 10, lineHeight: 1.5 }}>
        The last run used &quot;Run to here&quot; and stopped before this step.
        Click <span style={{ color: "#89b4fa" }}>Run all steps</span> to include it.
      </div>
    </div>
  );
}
