/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import { memo, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import { type NodeProps } from "@xyflow/react";

import MiniHitlCard from "../viewer/MiniHitlCard";
import { PROBE_STRATEGIES, getSubgraphLabel } from "../edges/probeStrategies";
import { usePipelineTest } from "../context/PipelineTestContext";

import { BaseNode, NodeHandle } from "./_base";

type ViewerMode = "auto" | "entities" | "verification" | "surface_forms" | "json";

interface MiniHitlConfig {
  label?: string;
  mode?: ViewerMode;
  onConfigure?: () => void;
}

function EmptySlate() {
  return (
    <div
      style={{
        color: "#6c7086",
        fontSize: 11,
        padding: "12px 8px",
        textAlign: "center",
        lineHeight: 1.5,
      }}
    >
      Connect this viewer to an upstream step,
      <br />
      then run a dry run to see clinical output here.
    </div>
  );
}

function GenericSummary({ output }: { output: Record<string, unknown> }) {
  const skip = new Set([
    "patient_id",
    "encounter_id",
    "candidate_id",
    "schema_version",
    "text",
    "errors",
  ]);
  const keys = Object.keys(output).filter((k) => !skip.has(k));
  if (keys.length === 0) {
    return (
      <div style={{ color: "#6c7086", fontSize: 10 }}>
        No structured output fields available.
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 4 }}>
      {keys.slice(0, 8).map((k) => {
        const v = output[k];
        const display =
          v == null
            ? "-"
            : Array.isArray(v)
              ? `${v.length} item${v.length === 1 ? "" : "s"}`
              : typeof v === "object"
                ? `${Object.keys(v as Record<string, unknown>).length} fields`
                : String(v).slice(0, 80);
        return (
          <div
            key={k}
            style={{
              display: "flex",
              gap: 6,
              fontSize: 10,
              fontFamily: "'JetBrains Mono', monospace",
              color: "#cdd6f4",
              alignItems: "flex-start",
            }}
          >
            <span
              style={{
                color: "#6c7086",
                minWidth: 90,
                flexShrink: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {k}
            </span>
            <span style={{ wordBreak: "break-word" }}>{display}</span>
          </div>
        );
      })}
      {keys.length > 8 && (
        <div style={{ color: "#6c7086", fontSize: 10 }}>
          ...{keys.length - 8} more fields
        </div>
      )}
    </div>
  );
}

function MiniHitlNodeComponent({ id, data, selected }: NodeProps) {
  const [jsonOpen, setJsonOpen] = useState(false);
  const { getViewerTraceSnapshot, runToStep } = usePipelineTest();

  const config = data as MiniHitlConfig;
  const snapshot = getViewerTraceSnapshot(id);
  const step = snapshot.step;
  const mode = config.mode ?? "auto";
  const subgraphId = step?.subgraph_id ?? "";
  const strategy = subgraphId ? PROBE_STRATEGIES[subgraphId] : undefined;

  const output: Record<string, unknown> =
    (step?.output_state as Record<string, unknown> | undefined) ?? {};
  const input: Record<string, unknown> =
    (step?.input_state as Record<string, unknown> | undefined) ?? {};

  const clinicalTextSnippet = useMemo(() => {
    const raw = input.text ?? output.text;
    if (typeof raw !== "string" || raw.trim().length === 0) return null;
    const clean = raw.replace(/\s+/g, " ").trim();
    return clean.length > 130 ? clean.slice(0, 130) + "..." : clean;
  }, [input.text, output.text]);

  const headline = useMemo(() => {
    if (!step) return "Awaiting dry run";
    if (mode === "json") return "JSON mode - use Inspect JSON to view raw output.";
    if (strategy) {
      try {
        return strategy.headline(output, input);
      } catch {
        return `Output captured from ${getSubgraphLabel(subgraphId)}.`;
      }
    }
    return `Output captured from ${getSubgraphLabel(subgraphId)}.`;
  }, [step, mode, strategy, subgraphId, output, input]);

  const subtitle = step
    ? `${getSubgraphLabel(step.subgraph_id)} - ${snapshot.source === "batch" ? `Batch - ${snapshot.candidateId?.slice(0, 8) ?? "selected"}` : "Single dry run"}`
    : "No trace data yet";

  const status =
    (step?.status as "completed" | "halted" | "error" | "running" | undefined) ??
    "idle";

  return (
    <>
      <BaseNode
        accentColor="#90A4AE"
        selected={selected}
        minWidth={340}
        maxWidth={400}
        ariaLabel={`${config.label ?? "Mini HITL"} preview - ${subtitle}`}
        onActivate={config.onConfigure}
        sx={{ p: 1.25 }}
      >
        <Tooltip title="Mini HITL preview node - click to configure" placement="top" arrow>
          <Box
            aria-hidden="true"
            sx={{ position: "absolute", right: 8, top: 8, color: "text.secondary" }}
          >
            <SmartToyIcon sx={{ fontSize: "0.95rem" }} />
          </Box>
        </Tooltip>

        <NodeHandle
          id="input"
          type="target"
          color="#546E7A"
          top="50%"
          tooltip="Input - traced output from any upstream step"
        />

        <MiniHitlCard
          title={config.label ?? "Mini HITL"}
          subtitle={subtitle}
          headline={headline}
          status={status}
          onRunToHere={() => runToStep(id)}
          onInspectJson={() => setJsonOpen(true)}
        >
          {clinicalTextSnippet && (
            <div
              style={{
                borderLeft: "3px solid #89b4fa",
                paddingLeft: 8,
                marginBottom: 8,
                color: "#a6adc8",
                fontSize: 10,
                fontStyle: "italic",
                lineHeight: 1.5,
                wordBreak: "break-word",
              }}
            >
              {clinicalTextSnippet}
            </div>
          )}

          {step && strategy && mode !== "json" ? (
            <strategy.Detail
              output={output}
              input={input}
              openInspector={() => setJsonOpen(true)}
            />
          ) : step && mode !== "json" ? (
            <GenericSummary output={output} />
          ) : (
            <EmptySlate />
          )}
        </MiniHitlCard>

        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ mt: 0.5, display: "block", fontSize: "0.6rem" }}
        >
          Click to configure
        </Typography>
      </BaseNode>

      <Dialog open={jsonOpen} onClose={() => setJsonOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ pb: 1 }}>
          {step ? `${getSubgraphLabel(subgraphId)} - Full Trace` : "Mini HITL - No trace yet"}
        </DialogTitle>
        <DialogContent dividers>
          {!step ? (
            <Typography variant="body2" color="text.secondary">
              No trace output available yet.
            </Typography>
          ) : (
            <Box
              component="pre"
              sx={{
                m: 0,
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: "0.72rem",
                fontFamily: "monospace",
              }}
            >
              {JSON.stringify(
                {
                  source: snapshot.source,
                  candidate_id: snapshot.candidateId,
                  step_id: step.step_id,
                  subgraph_id: step.subgraph_id,
                  status: step.status,
                  input_state: step.input_state,
                  output_state: step.output_state,
                },
                null,
                2,
              )}
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

export const MiniHitlNode = memo(MiniHitlNodeComponent);
