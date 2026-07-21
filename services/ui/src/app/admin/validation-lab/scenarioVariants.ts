/**
 * Map brainstorm ScenarioVariant cards onto createCase payloads.
 *
 * Atlas: DI-EB716E68 / DO-A0ADDB38
 *
 * Atlas trace:
 *   DO: DO-A0ADDB38
 *   DI: DI-EB716E68
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A0ADDB38")
 */
import type { CreateCasePayload, PmhCategory } from "./labApi";

export interface EquityBlock {
  ethnicityConceptId?: string | null;
  ethnicityTerm?: string | null;
  performanceStatusGrade?: number | null;
  comorbidityBand?: string | null;
  core20Decile?: number | null;
  plusGroup?: string | null;
}

export interface ScenarioVariant {
  variantId: string;
  targetRecId?: string | null;
  label: string;
  rationale: string;
  summary?: string | null;
  tags?: string[];
  recommended?: boolean;
  isControl?: boolean;
  expectedTrigger?: boolean | null;
  expectedTriggerReason?: string | null;
  title?: string | null;
  patientName?: string | null;
  patientAge?: string | null;
  patientSex?: string | null;
  referralText?: string | null;
  pmh?: Array<{
    category: PmhCategory;
    conceptId: string;
    term?: string;
  }>;
  observations?: Array<{
    observableId: string;
    value: number;
    unit: string;
    term?: string;
  }>;
  equity?: EquityBlock | null;
  triggerConceptIds?: string[];
}

export interface CreateCaseResult {
  variantId: string;
  ok: boolean;
  caseId?: string;
  error?: string;
}

export type CreateCaseFn = (
  payload: CreateCasePayload,
) => Promise<{ id: string }>;

function pick(
  raw: Record<string, unknown>,
  ...keys: string[]
): unknown {
  for (const key of keys) {
    if (raw[key] !== undefined && raw[key] !== null) return raw[key];
  }
  return undefined;
}

/** Coerce API / LLM variant payloads into a stable UI card shape. */
export function normaliseVariantFromApi(
  raw: Record<string, unknown>,
  index: number,
): ScenarioVariant {
  const variantId = String(
    pick(raw, "variantId", "variant_id") || `variant-${index + 1}`,
  ).trim();
  const title = String(pick(raw, "title", "caseTitle", "case_title") || "").trim();
  const label = String(
    pick(raw, "label", "name") || title || `Variant ${index + 1}`,
  ).trim();
  const rationale = String(
    pick(raw, "rationale", "reason", "why") ||
      "Proposed as a representative test-patient variant.",
  ).trim();
  const summary = String(
    pick(raw, "summary", "description", "blurb") || rationale,
  ).trim();
  const tagsRaw = pick(raw, "tags", "labels", "chips");
  const tags = Array.isArray(tagsRaw)
    ? tagsRaw
        .map((t) => String(t || "").trim())
        .filter(Boolean)
        .slice(0, 8)
    : [];
  const ageRaw = pick(raw, "patientAge", "patient_age");
  const pmhRaw = pick(raw, "pmh") ;
  const pmh = Array.isArray(pmhRaw)
    ? pmhRaw
        .filter((row): row is Record<string, unknown> => !!row && typeof row === "object")
        .map((row) => ({
          category: (String(row.category || "condition") as PmhCategory),
          conceptId: String(row.conceptId || row.concept_id || ""),
          term: String(row.term || ""),
        }))
        .filter((row) => row.conceptId)
    : [];
  const obsRaw = pick(raw, "observations");
  const observations = Array.isArray(obsRaw)
    ? obsRaw
        .filter((row): row is Record<string, unknown> => !!row && typeof row === "object")
        .map((row) => ({
          observableId: String(row.observableId || row.observable_id || ""),
          value: Number(row.value),
          unit: String(row.unit || ""),
          term: String(row.term || ""),
        }))
        .filter((row) => row.observableId && row.unit && Number.isFinite(row.value))
    : [];
  const equityRaw = pick(raw, "equity");
  const equity =
    equityRaw && typeof equityRaw === "object"
      ? (equityRaw as EquityBlock)
      : null;

  return {
    variantId,
    targetRecId: (pick(raw, "targetRecId", "target_rec_id") as string) || null,
    label,
    title: title || label,
    summary: summary || rationale,
    tags,
    rationale,
    recommended: Boolean(pick(raw, "recommended")),
    isControl: Boolean(pick(raw, "isControl", "is_control")),
    expectedTrigger:
      (pick(raw, "expectedTrigger", "expected_trigger") as boolean | null) ??
      null,
    expectedTriggerReason:
      (pick(raw, "expectedTriggerReason", "expected_trigger_reason") as string) ||
      null,
    patientName: (pick(raw, "patientName", "patient_name") as string) || null,
    patientAge: ageRaw == null || ageRaw === "" ? null : String(ageRaw),
    patientSex: (pick(raw, "patientSex", "patient_sex") as string) || null,
    referralText:
      (pick(raw, "referralText", "referral_text") as string) || null,
    pmh,
    observations,
    equity,
    triggerConceptIds: Array.isArray(pick(raw, "triggerConceptIds", "trigger_concept_ids"))
      ? (pick(raw, "triggerConceptIds", "trigger_concept_ids") as string[])
      : [],
  };
}

function parseAge(raw: string | null | undefined): number | null {
  if (raw == null || String(raw).trim() === "") return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

const DEFAULT_GP_PRACTICE = "Validation Lab GP Practice";

export function variantToCreatePayload(
  variant: ScenarioVariant,
): CreateCasePayload {
  const equity = variant.equity || {};
  return {
    title: String(variant.title || variant.label || "Brainstorm variant").trim(),
    summary: String(variant.summary || variant.rationale || "").trim().slice(0, 200),
    tags: (variant.tags || []).map((t) => String(t).trim()).filter(Boolean).slice(0, 8),
    patient_name: String(variant.patientName || "").trim(),
    patient_age: parseAge(variant.patientAge),
    patient_sex: variant.patientSex || null,
    referral_text: String(variant.referralText || "").trim(),
    case_type: "referral",
    gp_practice_name: DEFAULT_GP_PRACTICE,
    pmh: (variant.pmh || []).map((row) => ({
      category: row.category,
      concept_id: row.conceptId,
      term: row.term || "",
    })),
    encounters: [],
    ethnicity_concept_id: equity.ethnicityConceptId || null,
    ethnicity_term: equity.ethnicityTerm || null,
    performance_status_grade:
      equity.performanceStatusGrade == null
        ? null
        : Number(equity.performanceStatusGrade),
    comorbidity_band: equity.comorbidityBand || null,
    core20_decile:
      equity.core20Decile == null ? null : Number(equity.core20Decile),
    plus_group: equity.plusGroup || null,
    observations: (variant.observations || []).map((obs) => ({
      observable_id: obs.observableId,
      value: Number(obs.value),
      unit: obs.unit,
      term: obs.term || "",
    })),
  };
}

export async function createCasesFromVariants(
  variants: ScenarioVariant[],
  createCase: CreateCaseFn,
): Promise<CreateCaseResult[]> {
  const results: CreateCaseResult[] = [];
  for (const variant of variants) {
    try {
      const created = await createCase(variantToCreatePayload(variant));
      results.push({
        variantId: variant.variantId,
        ok: true,
        caseId: created.id,
      });
    } catch (err) {
      results.push({
        variantId: variant.variantId,
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }
  return results;
}
