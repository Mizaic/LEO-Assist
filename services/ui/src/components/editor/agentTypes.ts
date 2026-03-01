export type AgentModelSize = 'small' | 'big';

export interface AgentInterpretation {
  summary?: string;
  insights?: Array<string | Record<string, unknown>>;
  quality_checks?: Array<string | Record<string, unknown>>;
  recommended_measures?: Array<string | Record<string, unknown>>;
  follow_up_questions?: Array<string | Record<string, unknown>>;
}
