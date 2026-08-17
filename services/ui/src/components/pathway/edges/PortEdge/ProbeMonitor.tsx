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
 * ProbeMonitor -- the floating popover that surfaces what a pipeline
 * step produced once a probe is clamped on an edge (Phase 6b-vi
 * decomposition).
 *
 * Owns the local UI state (active tab, drag offset, drawer open) and
 * delegates each tab body to a focused presentational component. Also
 * handles Escape-to-close and drag-to-reposition.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useReactFlow } from "@xyflow/react";

import { usePipelineTest } from "../../context/PipelineTestContext";
import { PROBE_STRATEGIES, getSubgraphLabel } from "../probeStrategies";
import {
  HaltedBanner,
  NotReachedBanner,
  NotReachedByPartialRunBanner,
  PartialRunEndBanner,
} from "./ProbeMonitorBanners";
import { ProbeInspectorDrawer } from "./ProbeInspectorDrawer";
import { ProbeMonitorChanges } from "./ProbeMonitorChanges";
import { ProbeMonitorData } from "./ProbeMonitorData";
import { ProbeMonitorValidate } from "./ProbeMonitorValidate";
import {
  asPostProcessingTrace,
  type PathSegment,
  type ProbeTab,
  pluralize,
} from "./utils";
import {
  collectStateChanges,
  getMeaningfulHighlights,
  topLevelEntries,
} from "./diff";

interface MonitorProps {
  sourceId: string;
  targetId: string;
  x: number;
  y: number;
  onClose: () => void;
}

export function ProbeMonitor({ sourceId, targetId, x, y, onClose }: MonitorProps) {
  const {
    testTrace,
    isTestRunning,
    runningStepId,
    haltedNodeId,
    partialRunEndNodeId,
    runToStep,
    getNodeExpectedInputs,
  } = usePipelineTest();
  const [tab, setTab] = useState<ProbeTab>("changes");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedPath, setSelectedPath] = useState<PathSegment[]>([]);
  const [showAllChanges, setShowAllChanges] = useState(false);

  // Escape closes the topmost surface first (drawer), then the popover.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (drawerOpen) {
        setDrawerOpen(false);
        event.stopPropagation();
        return;
      }
      onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [drawerOpen, onClose]);

  const [dragOffset, setDragOffset] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isRaised, setIsRaised] = useState(false);
  const dragStart = useRef<{ mx: number; my: number; ox: number; oy: number } | null>(null);

  const handleDragMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    dragStart.current = { mx: e.clientX, my: e.clientY, ox: dragOffset.x, oy: dragOffset.y };
    setIsRaised(true);
    const onMove = (ev: MouseEvent) => {
      if (!dragStart.current) return;
      setDragOffset({
        x: dragStart.current.ox + ev.clientX - dragStart.current.mx,
        y: dragStart.current.oy + ev.clientY - dragStart.current.my,
      });
    };
    const onUp = () => {
      dragStart.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  };

  const sourceTrace = testTrace?.[sourceId] ?? null;
  const targetTrace = testTrace?.[targetId] ?? null;
  const isInjectedEdge = !sourceTrace && Boolean(targetTrace);
  const wireState: Record<string, unknown> | null = sourceTrace
    ? sourceTrace.output_state
    : (targetTrace ? targetTrace.input_state : null);
  const postProcessingTrace = asPostProcessingTrace(wireState?.post_processing_trace);
  const { getNode } = useReactFlow();
  const sourceSubgraphId = sourceTrace?.subgraph_id
    ?? ((getNode(sourceId)?.data as Record<string, unknown>)?.subgraphId as string)
    ?? "";
  const targetSubgraphId = targetTrace?.subgraph_id
    ?? ((getNode(targetId)?.data as Record<string, unknown>)?.subgraphId as string)
    ?? "";
  const strategy = PROBE_STRATEGIES[sourceSubgraphId] ?? null;
  const sourceLabel = sourceTrace?.label ?? getSubgraphLabel(sourceSubgraphId);
  const targetLabel = targetTrace?.label ?? getSubgraphLabel(targetSubgraphId);
  const wireStatus = sourceTrace?.status ?? (targetTrace ? "injected" : null);
  const wireDuration = sourceTrace?.duration_ms ?? null;
  const wireLabel = sourceTrace?.label ?? (isInjectedEdge ? `Injected into ${targetTrace?.label ?? targetId}` : null);
  const wireError = sourceTrace?.error ?? null;

  const isIntercepting = isTestRunning && (runningStepId === sourceId || runningStepId === targetId);
  const isPending = isTestRunning && !wireState && !isIntercepting;
  const entries = topLevelEntries(wireState);
  const highlights = getMeaningfulHighlights(entries);
  const stepChanges = useMemo(
    () => (
      sourceTrace
        ? collectStateChanges(sourceTrace.input_state, sourceTrace.output_state)
            .filter((change) => String(change.path[0] ?? "") !== "post_processing_trace")
        : []
    ),
    [sourceTrace],
  );
  const hadRetries = useMemo(() => {
    const attempts = sourceTrace?.output_state?.extraction_attempts;
    return Array.isArray(attempts) && (attempts as unknown[]).length > 1;
  }, [sourceTrace]);
  const hasSoftErrors = wireStatus === "completed" && stepChanges.some(
    (c) => String(c.path[0] ?? "").toLowerCase().includes("error") && c.kind === "added",
  );
  const sourceOutputEntries = useMemo(
    () => (sourceTrace ? topLevelEntries(sourceTrace.output_state) : []),
    [sourceTrace],
  );
  const changeCounts = useMemo(
    () => stepChanges.reduce(
      (summary, change) => {
        summary[change.kind] += 1;
        return summary;
      },
      { added: 0, changed: 0, removed: 0 },
    ),
    [stepChanges],
  );
  const changedRoots = useMemo(
    () => Array.from(new Set(stepChanges.map((change) => String(change.path[0] ?? "pipeline_state")))),
    [stepChanges],
  );
  const arrayCountDeltas = useMemo(() => {
    if (!sourceTrace) return [];
    const deltas: Array<{ key: string; before: number; after: number }> = [];
    const inp = sourceTrace.input_state;
    const out = sourceTrace.output_state;
    const keys = new Set([...Object.keys(inp ?? {}), ...Object.keys(out ?? {})]);
    for (const key of keys) {
      const b = inp?.[key];
      const a = out?.[key];
      if (Array.isArray(b) && Array.isArray(a) && b.length !== a.length) {
        deltas.push({ key, before: b.length, after: a.length });
      }
    }
    return deltas;
  }, [sourceTrace]);

  const produced = wireState ? Object.keys(wireState) : [];
  const expected = getNodeExpectedInputs(targetId);
  const matched = expected.filter((key) => produced.includes(key));
  const missing = expected.filter((key) => !produced.includes(key));
  const extra = produced.filter((key) => !expected.includes(key));
  const hasExpected = expected.length > 0;

  const isSourceHalted = sourceTrace?.status === "halted";
  const isEdgeNotReached = !isTestRunning && testTrace !== null && !sourceTrace && !!haltedNodeId;
  const isPartialRunEnd = !isTestRunning && sourceId === partialRunEndNodeId && !!sourceTrace;
  const isNotReachedByPartialRun = !isTestRunning && testTrace !== null && !sourceTrace && !!partialRunEndNodeId && !haltedNodeId;

  const statusColor = isSourceHalted
    ? "#f38ba8"
    : (wireStatus === "completed" || wireStatus === "injected")
      ? "#a6e3a1"
      : wireStatus === "error"
        ? "#f38ba8"
        : "#89b4fa";

  const openInspector = (path: PathSegment[]) => {
    setSelectedPath(path);
    setDrawerOpen(true);
  };

  const hadSourceTraceRef = useRef(false);
  useEffect(() => {
    if (!sourceTrace && tab === "changes") setTab("data");
    if (sourceTrace && !hadSourceTraceRef.current) {
      hadSourceTraceRef.current = true;
      setTab("changes");
    }
  }, [sourceTrace, tab]);

  const availableTabs: ProbeTab[] = sourceTrace ? ["changes", "data", "validate"] : ["data", "validate"];
  const changeSummaryBits = [
    changeCounts.added > 0 ? `added ${pluralize(changeCounts.added, "thing")}` : null,
    changeCounts.changed > 0 ? `changed ${pluralize(changeCounts.changed, "thing")}` : null,
    changeCounts.removed > 0 ? `removed ${pluralize(changeCounts.removed, "thing")}` : null,
  ].filter(Boolean);

  const liveInputState = (testTrace?.[runningStepId ?? ""]?.input_state ?? {}) as Record<string, unknown>;

  return (
    <>
      <div
        className="nodrag nopan"
        role="dialog"
        aria-label={`Probe ${sourceLabel || sourceId} to ${targetLabel || targetId}. Press Escape to close.`}
        style={{
          position: "absolute",
          transform: `translate(-50%, 0) translate(${x + dragOffset.x}px, ${y + 18 + dragOffset.y}px)`,
          pointerEvents: "all",
          background: "#1e1e2e",
          color: "#cdd6f4",
          borderRadius: 10,
          border: `2px solid ${statusColor}`,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
          fontSize: 11,
          minWidth: 520,
          maxWidth: 680,
          boxShadow: isRaised ? "0 16px 48px rgba(0,0,0,0.85)" : "0 8px 32px rgba(0,0,0,0.6)",
          zIndex: isRaised ? 1100 : 1000,
          overflow: "hidden",
          userSelect: dragStart.current ? "none" : "auto",
        }}
      >
        <div
          onMouseDown={handleDragMouseDown}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "5px 10px",
            background: "#313244",
            borderBottom: `1px solid ${statusColor}40`,
            cursor: dragStart.current ? "grabbing" : "grab",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ color: "#45475a", fontSize: 12, letterSpacing: 1 }}>⠿</span>
            <span style={{ fontSize: 13 }}>{strategy?.icon ?? "⊕"}</span>
            <span style={{ color: "#89b4fa", fontWeight: 700, fontSize: 10, letterSpacing: "0.05em" }}>PROBE</span>
            <span style={{ color: "#6c7086", fontSize: 10 }}>{sourceLabel || sourceId} → {targetLabel || targetId}</span>
          </span>
          <span onMouseDown={(e) => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <button
              onClick={() => runToStep(sourceId)}
              disabled={isTestRunning}
              title="Run the pipeline only up to this step"
              style={{
                background: isTestRunning ? "#45475a" : "#0d46d6",
                border: "none",
                borderRadius: 4,
                color: isTestRunning ? "#6c7086" : "#fff",
                cursor: isTestRunning ? "default" : "pointer",
                fontSize: 10,
                fontWeight: 700,
                padding: "2px 7px",
                letterSpacing: "0.03em",
              }}
            >
              {isTestRunning ? "running…" : "▶ Run to here"}
            </button>
            <button
              onClick={onClose}
              style={{
                background: "none",
                border: "none",
                color: "#f38ba8",
                cursor: "pointer",
                fontSize: 13,
                lineHeight: 1,
                padding: 0,
              }}
            >
              ✕
            </button>
          </span>
        </div>

        {isSourceHalted && <HaltedBanner sourceTrace={sourceTrace as { halt_reason?: string } | null} />}
        {isPartialRunEnd && <PartialRunEndBanner />}
        {isEdgeNotReached && <NotReachedBanner />}
        {isNotReachedByPartialRun && <NotReachedByPartialRunBanner />}

        {!isEdgeNotReached && wireState && (
          <div style={{
            display: "flex",
            gap: 0,
            background: "#181825",
            borderBottom: "1px solid #313244",
          }}>
            {availableTabs.map((section) => (
              <button
                key={section}
                onClick={() => setTab(section)}
                style={{
                  background: "none",
                  border: "none",
                  borderBottom: tab === section ? `2px solid ${statusColor}` : "2px solid transparent",
                  color: tab === section ? statusColor : "#6c7086",
                  cursor: "pointer",
                  fontSize: 10,
                  fontWeight: 700,
                  padding: "3px 10px",
                  letterSpacing: "0.04em",
                  textTransform: "uppercase",
                }}
              >
                {section === "changes"
                  ? `What's different${stepChanges.length > 0 ? ` (${stepChanges.length})` : ""}`
                  : section === "data"
                    ? (isInjectedEdge ? "Data going in" : "Results")
                    : `Wiring ${missing.length > 0 ? "⚠" : matched.length > 0 ? "✓" : ""}`}
              </button>
            ))}
          </div>
        )}

        {!isEdgeNotReached && wireState && (
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 10,
            padding: "4px 10px",
            background: "#181825",
            fontSize: 10,
            borderBottom: "1px solid #313244",
          }}>
            <span style={{ color: statusColor, fontWeight: 700 }}>
              {isSourceHalted ? "🛑 Halted" : wireStatus === "injected" ? "⬇ Data fed in" : wireStatus === "completed" ? "✓ Worked" : "✗ Problem"}
            </span>
            {wireDuration !== null && (
              <span style={{ color: "#6c7086" }}>
                took {wireDuration < 1000 ? `${wireDuration}ms` : `${(wireDuration / 1000).toFixed(1)}s`}
              </span>
            )}
            {sourceTrace && changeSummaryBits.length > 0 && (
              <span style={{ color: "#6c7086" }}>
                {changeSummaryBits.join(", ")}
              </span>
            )}
            <span style={{ color: "#6c7086" }}>{entries.length} field{entries.length === 1 ? "" : "s"} total</span>
            {wireLabel && <span style={{ color: "#6c7086" }}>{wireLabel}</span>}
          </div>
        )}

        <div style={{ padding: "8px 10px", maxHeight: "60vh", overflowY: "auto" }}>
          {tab === "changes" && sourceTrace && (
            <ProbeMonitorChanges
              strategy={strategy}
              sourceTrace={sourceTrace}
              stepChanges={stepChanges}
              changeCounts={changeCounts}
              changedRoots={changedRoots}
              arrayCountDeltas={arrayCountDeltas}
              sourceOutputEntries={sourceOutputEntries}
              postProcessingTrace={postProcessingTrace}
              targetSubgraphId={targetSubgraphId}
              produced={produced}
              hasSoftErrors={hasSoftErrors}
              hadRetries={hadRetries}
              wireStatus={wireStatus}
              showAllChanges={showAllChanges}
              onToggleAllChanges={() => setShowAllChanges((prev) => !prev)}
              hasExpected={hasExpected}
              matched={matched}
              missing={missing}
              extra={extra}
              openInspector={openInspector}
            />
          )}

          {tab === "data" && (
            <ProbeMonitorData
              isTestRunning={isTestRunning}
              wireState={wireState}
              isEdgeNotReached={isEdgeNotReached}
              isNotReachedByPartialRun={isNotReachedByPartialRun}
              isPending={isPending}
              isIntercepting={isIntercepting}
              liveInputState={liveInputState}
              entries={entries}
              highlights={highlights}
              wireError={wireError}
              openInspector={openInspector}
            />
          )}

          {tab === "validate" && wireState && (
            <ProbeMonitorValidate
              hasExpected={hasExpected}
              matched={matched}
              missing={missing}
              extra={extra}
              wireState={wireState}
              openInspector={openInspector}
            />
          )}
        </div>

        <style>{`
          @keyframes probeSpin  { to { transform: rotate(360deg); } }
          @keyframes probePulse { 0%,100% { opacity:1; } 50% { opacity:0.3; } }
        `}</style>
      </div>

      {wireState && selectedPath.length > 0 && (
        <ProbeInspectorDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          wireState={wireState}
          selectedPath={selectedPath}
          onSelectPath={setSelectedPath}
        />
      )}
    </>
  );
}
