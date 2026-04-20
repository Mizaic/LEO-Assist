/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
export type AgentModelSize = 'small' | 'big';

export interface AgentInterpretation {
  summary?: string;
  insights?: Array<string | Record<string, unknown>>;
  quality_checks?: Array<string | Record<string, unknown>>;
  recommended_measures?: Array<string | Record<string, unknown>>;
  follow_up_questions?: Array<string | Record<string, unknown>>;
}
