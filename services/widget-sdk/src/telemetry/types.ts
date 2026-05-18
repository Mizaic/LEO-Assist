/**
 * Telemetry payload types.
 *
 * Atlas trace:
 *   DO: DO-23DDE984
 *   DI: DI-5F121122
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-23DDE984")
 */

export type TelemetryEventType =
  | "loaded"
  | "error"
  | "disclosure-opened"
  | "disclosure-closed"
  | "source-id-clicked";

export interface TelemetryEnvelope {
  readonly widget_instance_id: string;
  readonly event_id: number;
  readonly type: TelemetryEventType;
  readonly assessment_id: string;
  readonly emitted_at_ms: number;
  readonly payload: Readonly<Record<string, unknown>>;
}
