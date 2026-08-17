/**
 * Atlas trace:
 *   DI: DI-3F771AFB
 */

export interface RangeDraft {
  orgId: string;
  sex: string;
  ageMin: string;
  ageMax: string;
  low: string;
  high: string;
  critLow: string;
  critHigh: string;
  source: string;
}

export const EMPTY_RANGE: RangeDraft = {
  orgId: "",
  sex: "all",
  ageMin: "",
  ageMax: "",
  low: "",
  high: "",
  critLow: "",
  critHigh: "",
  source: "manual",
};

export function sexLabel(value: string): string {
  if (value === "male") return "Male";
  if (value === "female") return "Female";
  return "All";
}

export function ageCopy(min: string, max: string): string {
  if (!min.trim() && !max.trim()) return "Any age";
  if (min.trim() && !max.trim()) return min.trim() + " years and over";
  if (!min.trim() && max.trim()) return "Up to " + max.trim() + " years";
  return min.trim() + " to " + max.trim() + " years";
}

export function bandCopy(low: string, high: string, empty: string): string {
  if (!low.trim() && !high.trim()) return empty;
  return (low.trim() || "none") + " to " + (high.trim() || "none");
}

export interface RangeOrgOption {
  id: string;
  name: string;
  type?: string;
  odsCode?: string;
}

export const PLATFORM_OWNER: RangeOrgOption = {
  id: "",
  name: "Platform default",
};

export function ownerCopy(orgId: string, orgName?: string): string {
  if (!orgId.trim()) return PLATFORM_OWNER.name;
  return orgName?.trim() || orgId;
}

export function orgSearchLabel(org: RangeOrgOption): string {
  if (!org.id) return PLATFORM_OWNER.name;
  const extra = [org.type, org.odsCode].filter(Boolean).join(" · ");
  return extra ? org.name + " · " + extra : org.name;
}

export function filterRangeOrgs(
  options: RangeOrgOption[],
  state: { inputValue: string },
): RangeOrgOption[] {
  const query = state.inputValue.trim().toLowerCase();
  const platform = options.filter((row) => !row.id);
  if (query.length < 2) return platform;
  return options.filter((row) => orgMatchesQuery(row, query));
}

function orgMatchesQuery(row: RangeOrgOption, query: string): boolean {
  if (!row.id) return true;
  return (
    row.name.toLowerCase().includes(query) ||
    (row.odsCode || "").toLowerCase().includes(query) ||
    (row.type || "").toLowerCase().includes(query)
  );
}

export function rangeConfirmRows(draft: RangeDraft, orgName?: string) {
  return [
    { label: "Owner", value: ownerCopy(draft.orgId, orgName) },
    { label: "Sex", value: sexLabel(draft.sex) },
    { label: "Age", value: ageCopy(draft.ageMin, draft.ageMax) },
    { label: "Normal", value: bandCopy(draft.low, draft.high, "Not set") },
    { label: "Critical", value: bandCopy(draft.critLow, draft.critHigh, "Not set") },
    { label: "Source", value: draft.source.trim() || "manual" },
  ];
}
