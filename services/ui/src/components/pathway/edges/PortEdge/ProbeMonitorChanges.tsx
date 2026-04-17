"use client";

/**
 * "What's different" tab body for the ProbeMonitor (Phase 6b-vi
 * decomposition).
 *
 * Renders the strategy headline, optional detail card, post-processing
 * trace summary, and the per-change diff list. All inspector hooks are
 * passed in from the parent so this stays presentational.
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  type PathSegment,
  type PostProcessingLayerTrace,
  type StateChange,
  describePath,
  friendlyError,
  pluralize,
  previewForAdded,
  previewForChange,
  summarizeValue,
  valueTone,
} from "./utils";
import { labelForChange, resolveInspectablePath, toneForChange } from "./diff";
import { TargetHint } from "../probeStrategies";
import type { ProbeStrategy } from "../probes/_shared";

interface ChangesTabProps {
  strategy: ProbeStrategy | null;
  sourceTrace: {
    input_state: Record<string, unknown> | null;
    output_state: Record<string, unknown> | null;
  };
  stepChanges: StateChange[];
  changeCounts: { added: number; changed: number; removed: number };
  changedRoots: string[];
  arrayCountDeltas: Array<{ key: string; before: number; after: number }>;
  sourceOutputEntries: Array<[string, unknown]>;
  postProcessingTrace: PostProcessingLayerTrace[];
  targetSubgraphId: string;
  produced: string[];
  hasSoftErrors: boolean;
  hadRetries: boolean;
  wireStatus: string | null;
  showAllChanges: boolean;
  onToggleAllChanges: () => void;
  hasExpected: boolean;
  matched: string[];
  missing: string[];
  extra: string[];
  openInspector: (path: PathSegment[]) => void;
}

export function ProbeMonitorChanges(props: ChangesTabProps) {
  const {
    strategy,
    sourceTrace,
    stepChanges,
    changeCounts,
    changedRoots,
    arrayCountDeltas,
    sourceOutputEntries,
    postProcessingTrace,
    targetSubgraphId,
    produced,
    hasSoftErrors,
    hadRetries,
    wireStatus,
    showAllChanges,
    onToggleAllChanges,
    hasExpected,
    matched,
    missing,
    extra,
    openInspector,
  } = props;

  const changeSummaryBits = [
    changeCounts.added > 0 ? `added ${pluralize(changeCounts.added, "thing")}` : null,
    changeCounts.changed > 0 ? `changed ${pluralize(changeCounts.changed, "thing")}` : null,
    changeCounts.removed > 0 ? `removed ${pluralize(changeCounts.removed, "thing")}` : null,
  ].filter(Boolean);

  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ border: "1px solid #313244", borderRadius: 8, padding: "8px 9px", background: "#181825" }}>
        <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
          {strategy ? `${strategy.icon} What happened` : "What happened"}
        </div>
        <div style={{ color: "#cdd6f4", fontSize: strategy ? 12 : 11, lineHeight: 1.45 }}>
          {strategy
            ? strategy.headline(sourceTrace.output_state ?? {}, sourceTrace.input_state ?? {})
            : stepChanges.length === 0
              ? "Nothing changed — data passed straight through."
              : `This step ${changeSummaryBits.join(", ")} in ${pluralize(changedRoots.length, "area")}.`}
        </div>
        {arrayCountDeltas.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6, fontSize: 10 }}>
            {arrayCountDeltas.map(({ key, before, after }) => (
              <span key={key} style={{ color: "#fab387", fontFamily: "monospace" }}>
                {key}: {before} → {after}
              </span>
            ))}
          </div>
        )}
        {!strategy && changedRoots.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {changedRoots.slice(0, 6).map((root) => (
              <button
                key={root}
                type="button"
                onClick={() => openInspector([root])}
                style={{
                  borderRadius: 999,
                  border: "1px solid #313244",
                  background: "#11111b",
                  color: "#89b4fa",
                  padding: "3px 8px",
                  fontSize: 10,
                  cursor: "pointer",
                }}
              >
                {root}
              </button>
            ))}
            {changedRoots.length > 6 && (
              <span style={{ color: "#6c7086", fontSize: 10, alignSelf: "center" }}>
                +{changedRoots.length - 6} more
              </span>
            )}
          </div>
        )}
      </div>

      {strategy && (
        <div style={{ border: "1px solid #313244", borderRadius: 8, padding: "8px 9px", background: "#181825" }}>
          {strategy.Detail({
            output: sourceTrace.output_state ?? {},
            input: sourceTrace.input_state ?? {},
            openInspector,
          })}
        </div>
      )}

      {!strategy && sourceOutputEntries.length > 0 && (
        <div style={{ border: "1px solid #313244", borderRadius: 8, padding: "8px 9px", background: "#181825" }}>
          <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, marginBottom: 6, letterSpacing: "0.04em", textTransform: "uppercase" }}>
            What this step produced
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
            {sourceOutputEntries.slice(0, 12).map(([key, value]) => (
              <button
                key={key}
                type="button"
                onClick={() => openInspector([key])}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 6,
                  width: "100%",
                  textAlign: "left",
                  border: key === "verification_result" ? "1px solid #a6adc8" : "1px solid #313244",
                  background: "#11111b",
                  borderRadius: 6,
                  padding: "4px 7px",
                  color: "#cdd6f4",
                  cursor: "pointer",
                }}
              >
                <span style={{ color: key === "verification_result" ? "#f9e2af" : "#89b4fa", fontFamily: "monospace", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {key}
                </span>
                <span style={{ color: valueTone(value), fontSize: 10, flexShrink: 0 }}>
                  {summarizeValue(value)}
                </span>
              </button>
            ))}
          </div>
          {sourceOutputEntries.length > 12 && (
            <div style={{ color: "#6c7086", fontSize: 10, marginTop: 4 }}>
              …and {sourceOutputEntries.length - 12} more
            </div>
          )}
        </div>
      )}

      {!strategy && postProcessingTrace.length > 0 && (
        <PostProcessingTraceTable trace={postProcessingTrace} />
      )}

      {targetSubgraphId && <TargetHint targetSubgraphId={targetSubgraphId} producedKeys={produced} />}

      {strategy && stepChanges.length > 0 && (
        <button
          type="button"
          onClick={onToggleAllChanges}
          style={{
            background: "none", border: "none", color: "#6c7086",
            cursor: "pointer", fontSize: 10, textAlign: "left", padding: "4px 0",
          }}
        >
          {showAllChanges ? "▾ Hide" : "▸ Show"} {stepChanges.length} individual changes
        </button>
      )}

      {(!strategy || showAllChanges) && (stepChanges.length === 0 ? (
        <div style={{ color: "#6c7086", fontSize: 11 }}>
          Everything stayed the same — no differences found.
        </div>
      ) : (
        <ChangeList
          stepChanges={stepChanges}
          sourceOutput={sourceTrace.output_state}
          hasSoftErrors={hasSoftErrors}
          hadRetries={hadRetries}
          wireStatus={wireStatus}
          openInspector={openInspector}
        />
      ))}

      {hasExpected && (
        <div style={{ borderTop: "1px solid #313244", padding: "6px 4px 2px", marginTop: 6, fontSize: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
          <span style={{ color: "#89b4fa", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.04em" }}>Wiring</span>
          {matched.length > 0 && <span style={{ color: "#a6e3a1" }}>✓ {matched.join(", ")} reaching next step</span>}
          {missing.length > 0 && <span style={{ color: "#f38ba8" }}>✗ Missing: {missing.join(", ")}</span>}
          {extra.length > 0 && <span style={{ color: "#6c7086" }}>also has: {extra.slice(0, 4).join(", ")}{extra.length > 4 ? ` +${extra.length - 4}` : ""}</span>}
        </div>
      )}
    </div>
  );
}

function PostProcessingTraceTable({ trace }: { trace: PostProcessingLayerTrace[] }) {
  return (
    <div style={{ border: "1px solid #313244", borderRadius: 8, overflow: "hidden", background: "#181825" }}>
      <div style={{ color: "#89b4fa", fontSize: 10, fontWeight: 700, padding: "7px 9px", letterSpacing: "0.04em", textTransform: "uppercase", borderBottom: "1px solid #313244" }}>
        Did each clean-up step run?
      </div>
      {trace.map((layer, i) => {
        const isSkipped = layer.status === "skipped";
        const isError = layer.status === "error";
        const statusColor = isError ? "#f38ba8" : isSkipped ? "#6c7086" : "#a6e3a1";
        const statusIcon = isError ? "✗" : isSkipped ? "○" : "✓";
        const statusLabel = isError ? "Error" : isSkipped ? "Skipped" : "Ran OK";
        const delta = layer.after_count - layer.before_count;
        const hasChanges = layer.added_count > 0 || layer.removed_count > 0 || layer.updated_count > 0;
        const changeParts: string[] = [];
        if (layer.added_count > 0) changeParts.push(`+${layer.added_count} added`);
        if (layer.removed_count > 0) changeParts.push(`−${layer.removed_count} removed`);
        if (layer.updated_count > 0) changeParts.push(`${layer.updated_count} updated`);
        const changeText = isSkipped ? "—" : hasChanges ? changeParts.join(", ") : "no change";
        const changeColor = delta < 0 ? "#f38ba8" : delta > 0 ? "#a6e3a1" : "#6c7086";
        return (
          <div
            key={layer.layer_id}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto auto",
              alignItems: "center",
              gap: 10,
              padding: "5px 9px",
              borderBottom: i < trace.length - 1 ? "1px solid #31324440" : "none",
              opacity: isSkipped ? 0.6 : 1,
            }}
          >
            <span style={{ color: "#cdd6f4", fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {layer.name}
            </span>
            <span style={{ color: changeColor, fontSize: 10, whiteSpace: "nowrap" }}>
              {changeText}
            </span>
            <span style={{ color: statusColor, fontSize: 10, fontWeight: 700, whiteSpace: "nowrap", minWidth: 60, textAlign: "right" }}>
              {statusIcon} {statusLabel}
            </span>
          </div>
        );
      })}
    </div>
  );
}

interface ChangeListProps {
  stepChanges: StateChange[];
  sourceOutput: Record<string, unknown> | null;
  hasSoftErrors: boolean;
  hadRetries: boolean;
  wireStatus: string | null;
  openInspector: (path: PathSegment[]) => void;
}

function ChangeList({
  stepChanges,
  sourceOutput,
  hasSoftErrors,
  hadRetries,
  wireStatus,
  openInspector,
}: ChangeListProps) {
  return (
    <div style={{ display: "grid", gap: 3 }}>
      {hasSoftErrors && (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "5px 7px",
          borderRadius: 6,
          background: "#fab38712",
          border: "1px solid #fab38740",
          fontSize: 10,
          color: "#fab387",
        }}>
          <span>{hadRetries ? "↺" : "⚠"}</span>
          <span>
            {hadRetries
              ? "A retry succeeded — the ⚠ error rows below are from earlier failed attempts."
              : "These errors are non-fatal — the step logged them and carried on."}
          </span>
        </div>
      )}
      {stepChanges.map((change, index) => {
        const inspectPath = resolveInspectablePath(sourceOutput, change.path);
        const canInspect = inspectPath.length > 0;
        const isErrorField = String(change.path[0] ?? "").toLowerCase().includes("error");
        const isSoftError = isErrorField && change.kind === "added" && wireStatus === "completed";
        const rawBefore = change.kind === "added" ? "—" : previewForChange(change.beforeValue, change.path, 2);
        const rawAfter = change.kind === "removed" ? "—" : previewForAdded(change.afterValue, change.path);
        const beforePreview = isErrorField ? friendlyError(rawBefore) : rawBefore;
        const afterPreview = isErrorField ? friendlyError(rawAfter) : rawAfter;
        const rowLabel = isSoftError ? "⚠" : labelForChange(change.kind);
        const rowLabelColor = isSoftError ? "#fab387" : toneForChange(change.kind);
        return (
          <button
            key={`${describePath(change.path)}:${index}`}
            type="button"
            onClick={() => { if (canInspect) openInspector(inspectPath); }}
            disabled={!canInspect}
            style={{
              display: "grid",
              gridTemplateColumns: "54px 1fr auto",
              gap: 6,
              alignItems: "baseline",
              width: "100%",
              textAlign: "left",
              border: "none",
              borderBottom: "1px solid #31324440",
              background: "transparent",
              padding: "4px 4px",
              color: "#cdd6f4",
              cursor: canInspect ? "pointer" : "default",
              opacity: canInspect ? 1 : 0.7,
            }}
          >
            <span style={{ fontSize: 9, fontWeight: 700, color: rowLabelColor }}>
              {rowLabel}
            </span>
            <span style={{ minWidth: 0 }}>
              <span style={{ color: "#89b4fa", fontFamily: "monospace", fontSize: 10 }}>
                {describePath(change.path)}
              </span>
              {" "}
              <span style={{ color: isSoftError ? "#fab38799" : "#6c7086", fontSize: 10 }}>
                {change.kind === "removed"
                  ? beforePreview
                  : change.kind === "added"
                    ? afterPreview
                    : `${beforePreview} → ${afterPreview}`}
              </span>
            </span>
            {canInspect && <span style={{ color: "#45475a", fontSize: 9 }}>→</span>}
          </button>
        );
      })}
    </div>
  );
}
