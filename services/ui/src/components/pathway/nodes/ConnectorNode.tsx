/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-B5DB3744
 *   DI: DI-C6700F52
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-B5DB3744")
 */
"use client";

import { memo } from "react";
import Chip from "@mui/material/Chip";
import { type NodeProps } from "@xyflow/react";

import { BaseNode, NodeHandle, NodeHeader } from "./_base";

const QUEUE_ACCENT = "#795548";
const REST_ACCENT = "#3F51B5";
const INPUT_PORT_COLOR = "#90A4AE";
const OUTPUT_PORT_COLOR = "#26A69A";

interface ConnectorNodeData {
  label?: string;
  connectorType?: "rest_connector" | "queue_publish";
  inputPorts?: string[];
  outputPorts?: string[];
  onConfigure?: () => void;
}

function ConnectorNodeComponent({ data, selected }: NodeProps) {
  const d = data as ConnectorNodeData;
  const connectorType = d.connectorType ?? "rest_connector";
  const isQueue = connectorType === "queue_publish";
  const accent = isQueue ? QUEUE_ACCENT : REST_ACCENT;
  const label = d.label || (isQueue ? "Queue Publish" : "REST API Call");
  const inputs = d.inputPorts ?? ["input"];
  const outputs = isQueue ? [] : (d.outputPorts ?? ["connector_response"]);

  return (
    <BaseNode
      accentColor={accent}
      selected={selected}
      borderStyle="dashed"
      minWidth={200}
      ariaLabel={`${label} connector node`}
      onActivate={d.onConfigure}
    >
      {inputs.map((name, i) => (
        <NodeHandle
          key={`in-${name}`}
          id={name}
          type="target"
          color={INPUT_PORT_COLOR}
          top={`${((i + 1) / (inputs.length + 1)) * 100}%`}
          tooltip={`Input ${name}`}
        />
      ))}
      {outputs.map((name, i) => (
        <NodeHandle
          key={`out-${name}`}
          id={name}
          type="source"
          color={OUTPUT_PORT_COLOR}
          top={`${((i + 1) / (outputs.length + 1)) * 100}%`}
          tooltip={`Output ${name}`}
        />
      ))}
      <NodeHeader title={label} />
      <Chip
        size="small"
        label={connectorType}
        sx={{
          mt: 0.5,
          bgcolor: accent,
          color: "#fff",
          fontSize: "0.62rem",
          height: 20,
        }}
      />
    </BaseNode>
  );
}

export const ConnectorNode = memo(ConnectorNodeComponent);
