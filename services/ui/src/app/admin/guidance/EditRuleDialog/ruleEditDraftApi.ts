/**
 * Client for Neo4j-backed rule-edit draft persistence (DI-D52E923B).
 *
 * Atlas: DI-D52E923B / DO-BED08F09 / VT-35051473
 */

export interface RuleEditDraftWizardState {
  currentStepId?: string;
  wizardPhase?: string | null;
  situationCount?: number;
  reachedCheck?: boolean;
  actionsDirty?: boolean;
}

export interface RuleEditDraft {
  draft_id: string;
  rule_id: string;
  rule_status?: string;
  name: string;
  reason: string;
  logic_tree: Record<string, unknown>;
  actions?: Array<Record<string, unknown>> | null;
  priority?: string | null;
  due_days?: number | null;
  is_default?: boolean | null;
  wizard_state: RuleEditDraftWizardState;
  updated_at: string;
}

export interface RuleEditDraftPutBody {
  reviewer: string;
  name: string;
  reason: string;
  logic_tree: Record<string, unknown>;
  actions?: Array<Record<string, unknown>> | null;
  priority?: string | null;
  due_days?: number | null;
  is_default?: boolean | null;
  wizard_state: RuleEditDraftWizardState;
}

const DEFAULT_REVIEWER = "admin";

export function draftReviewer(): string {
  return DEFAULT_REVIEWER;
}

async function readErrorMsg(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    if (typeof body?.detail === "string") return body.detail;
    return resp.statusText || `Request failed (${resp.status})`;
  } catch {
    return resp.statusText || `Request failed (${resp.status})`;
  }
}

export async function fetchRuleEditDraft(
  ruleId: string,
  reviewer: string = DEFAULT_REVIEWER,
): Promise<RuleEditDraft | null> {
  const resp = await fetch(
    `/api/guidance/rules/review/${encodeURIComponent(ruleId)}/draft?reviewer=${encodeURIComponent(reviewer)}`,
  );
  if (!resp.ok) {
    throw new Error(await readErrorMsg(resp));
  }
  const data = (await resp.json()) as { draft: RuleEditDraft | null };
  return data.draft ?? null;
}

export async function putRuleEditDraft(
  ruleId: string,
  body: RuleEditDraftPutBody,
): Promise<{ draft_id: string; rule_status: string; updated_at: string }> {
  const resp = await fetch(
    `/api/guidance/rules/review/${encodeURIComponent(ruleId)}/draft`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!resp.ok) {
    throw new Error(await readErrorMsg(resp));
  }
  return resp.json();
}

export async function discardRuleEditDraft(
  ruleId: string,
  reviewer: string = DEFAULT_REVIEWER,
): Promise<void> {
  const resp = await fetch(
    `/api/guidance/rules/review/${encodeURIComponent(ruleId)}/draft?reviewer=${encodeURIComponent(reviewer)}`,
    { method: "DELETE" },
  );
  if (!resp.ok) {
    throw new Error(await readErrorMsg(resp));
  }
}
