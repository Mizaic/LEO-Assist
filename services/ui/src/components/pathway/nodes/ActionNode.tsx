"use client";

import { memo, useMemo, useState } from "react";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { type NodeProps } from "@xyflow/react";

import { getPortsFromDescriptor, SUBGRAPH_OPTIONS } from "../config/subgraphs";
import type { ActionNodeData, PortDefinition } from "../config/types";
import { usePipelineTest } from "../context/PipelineTestContext";

import {
  BaseNode,
  NodeHandle,
  NodeHeader,
  NodeStatusStrip,
  PORT_COLORS,
  type BaseNodeTone,
  type NodeRunStatus,
} from "./_base";

interface ActionStepResult {
  status?: string;
  duration_ms?: number;
  output_state?: Record<string, unknown> | null;
  error?: string | null;
}

function buildHaltedDetail(stepResult: ActionStepResult | null): string {
  const fallback = "Pipeline stopped here - check the probe for details";
  const outputState = stepResult?.output_state ?? null;
  const verification = outputState?.verification_result as
    | Record<string, unknown>
    | undefined;
  if (!verification) return fallback;

  const parts: string[] = [];
  const confidence = verification.confidence;
  const threshold = outputState?.confidence_threshold;
  if (typeof confidence === "number") {
    if (typeof threshold === "number") {
      parts.push(
        `verification confidence ${confidence.toFixed(2)} < threshold ${threshold.toFixed(2)}`,
      );
    } else {
      parts.push(`verification confidence ${confidence.toFixed(2)}`);
    }
  }
  if (verification.is_accurate === false) parts.push("is_accurate=false");
  const issues = Array.isArray(verification.issues)
    ? verification.issues.map((i) => String(i)).filter(Boolean)
    : [];
  if (issues.length > 0) parts.push(issues.slice(0, 2).join("; "));
  return parts.length > 0
    ? `Pipeline stopped here - ${parts.join(" - ")}`
    : "Pipeline stopped here - verification gate failed";
}

function resolveRunStatus(
  isThisRunning: boolean,
  isHalted: boolean,
  isNotReached: boolean,
  stepStatus: string | undefined,
  isTestRunning: boolean,
  hasResult: boolean,
): NodeRunStatus {
  if (isThisRunning) return "running";
  if (isHalted) return "halted";
  if (isNotReached) return "skipped";
  if (stepStatus === "completed") return "completed";
  if (stepStatus === "error") return "error";
  if (isTestRunning && !hasResult) return "queued";
  return "idle";
}

function PortLabel({
  side,
  topPct,
  text,
}: {
  side: "left" | "right";
  topPct: string;
  text: string;
}) {
  return (
    <Typography
      variant="caption"
      sx={{
        position: "absolute",
        [side]: -8,
        top: topPct,
        transform: `translateY(-50%) translateX(${side === "left" ? "-100%" : "100%"})`,
        fontFamily: "monospace",
        fontSize: "0.62rem",
        color: "text.secondary",
        whiteSpace: "nowrap",
        pointerEvents: "none",
        [side === "left" ? "pr" : "pl"]: 0.5,
      }}
    >
      {text}
    </Typography>
  );
}

function ActionNodeComponent({ id, data, selected }: NodeProps) {
  const actionData = data as unknown as ActionNodeData;
  const [outputHovered, setOutputHovered] = useState(false);
  const { testTrace, isTestRunning, runningStepId, haltedNodeId } =
    usePipelineTest();
  const stepResult = (testTrace?.[id] ?? null) as ActionStepResult | null;
  const isThisRunning = isTestRunning && runningStepId === id;
  const isHalted = stepResult?.status === "halted";
  const isNotReached =
    testTrace !== null && !stepResult && !isThisRunning && !!haltedNodeId;
  const hasResult = !!stepResult;

  const subgraphLabel = useMemo(
    () =>
      SUBGRAPH_OPTIONS.find((s) => s.id === actionData.subgraphId)?.label ??
      actionData.subgraphId,
    [actionData.subgraphId],
  );

  const ports: PortDefinition[] = useMemo(
    () =>
      getPortsFromDescriptor(actionData.subgraphId, actionData.fieldMappings),
    [actionData.subgraphId, actionData.fieldMappings],
  );

  const inputs = ports.filter((p) => p.direction === "input");
  const outputs = ports.filter((p) => p.direction === "output");
  const hasOutputs = outputs.length > 0;

  const haltedDetail = useMemo(
    () => (isHalted ? buildHaltedDetail(stepResult) : undefined),
    [isHalted, stepResult],
  );

  const runStatus = resolveRunStatus(
    isThisRunning,
    isHalted,
    isNotReached,
    stepResult?.status,
    isTestRunning,
    hasResult,
  );

  const baseTone: BaseNodeTone = isHalted
    ? "halted"
    : isThisRunning
      ? "running"
      : "neutral";

  return (
    <BaseNode
      accentColor={actionData.color}
      selected={selected}
      runStatus={baseTone}
      notReached={isNotReached}
      minWidth={220}
      ariaLabel={`${actionData.label} - ${subgraphLabel}`}
      onActivate={actionData.onConfigure}
    >
      {inputs.map((port, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <NodeHandle
            key={`in-${port.key}`}
            id={port.key}
            type="target"
            color={PORT_COLORS[port.dataType]}
            top={topPct}
            tooltip={`Input ${port.key} - drag a connection here from a previous step`}
          />
        );
      })}
      {inputs.map((port, i) => {
        const topPct = `${((i + 1) / (inputs.length + 1)) * 100}%`;
        return (
          <PortLabel
            key={`in-label-${port.key}`}
            side="left"
            topPct={topPct}
            text={port.key}
          />
        );
      })}

      <NodeHeader
        title={actionData.label}
        trailing={
          <NodeStatusStrip
            status={runStatus}
            durationMs={stepResult?.duration_ms}
            detail={haltedDetail}
          />
        }
      />
      <Chip
        label={subgraphLabel}
        size="small"
        sx={{
          mt: 0.5,
          bgcolor: actionData.color,
          color: "#fff",
          fontSize: "0.65rem",
          height: 20,
        }}
      />

      {outputs.map((port, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <NodeHandle
            key={`out-${port.key}`}
            id={port.key}
            type="source"
            color={PORT_COLORS[port.dataType]}
            top={topPct}
            tooltip={`Output ${port.key} - drag this dot to connect to the next step`}
            onMouseEnter={() => setOutputHovered(true)}
            onMouseLeave={() => setOutputHovered(false)}
          />
        );
      })}
      {outputs.map((port, i) => {
        const topPct = `${((i + 1) / (outputs.length + 1)) * 100}%`;
        return (
          <PortLabel
            key={`out-label-${port.key}`}
            side="right"
            topPct={topPct}
            text={port.key}
          />
        );
      })}

      {!hasOutputs && (
        <Typography
          variant="caption"
          sx={{
            position: "absolute",
            right: -108,
            top: "50%",
            transform: "translateY(-50%)",
            width: 100,
            color: "text.disabled",
            fontSize: "0.6rem",
            lineHeight: 1.3,
            textAlign: "left",
          }}
        >
          Configure step to add outputs
        </Typography>
      )}

      {hasOutputs && outputHovered && (
        <Typography
          variant="caption"
          sx={{
            position: "absolute",
            right: -108,
            top: "calc(50% + 18px)",
            transform: "translateY(-50%)",
            width: 100,
            color: "primary.main",
            fontSize: "0.58rem",
            lineHeight: 1.3,
            pointerEvents: "none",
          }}
        >
          Drag dot to connect
        </Typography>
      )}
    </BaseNode>
  );
}

export const ActionNode = memo(ActionNodeComponent);
