/**
 * URL param serialisation and deserialisation for Mission Control filters.
 *
 * This is the single place that maps filter state <-> URL search params.
 * Deep-links from the audit page use these serialised params.
 *
 * Atlas trace:
 *   DO: DO-EE78E305
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-EE78E305")
 */
export interface MissionControlFilters {
  dateFrom: string;
  dateTo: string;
  orgId: string;
  patientId: string;
  pathwayFilter: "confirmed" | "closures" | "all";
  cancerTypes: string[];
  closureReasons: string[];
  reviewStatus: "all" | "reviewed" | "unreviewed";
  sortBy: string;
  sortDir: "ASC" | "DESC";
  page: number;
  pageSize: number;
}

export const DEFAULT_FILTERS: MissionControlFilters = {
  dateFrom: "",
  dateTo: "",
  orgId: "",
  patientId: "",
  pathwayFilter: "all",
  cancerTypes: [],
  closureReasons: [],
  reviewStatus: "all",
  sortBy: "referral_date",
  sortDir: "DESC",
  page: 1,
  pageSize: 25,
};

/** Serialise filter state to URLSearchParams. */
export function serialiseFilters(filters: MissionControlFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (filters.dateFrom) p.set("date_from", filters.dateFrom);
  if (filters.dateTo) p.set("date_to", filters.dateTo);
  if (filters.orgId) p.set("org_id", filters.orgId);
  const urlPatientId = filters.patientId.trim();
  if (urlPatientId) p.set("patient_id", urlPatientId);
  if (filters.pathwayFilter !== "all") p.set("pathway_filter", filters.pathwayFilter);
  if (filters.cancerTypes.length) p.set("cancer_types", filters.cancerTypes.join(","));
  if (filters.closureReasons.length) p.set("closure_reasons", filters.closureReasons.join(","));
  if (filters.reviewStatus !== "all") p.set("review_status", filters.reviewStatus);
  if (filters.sortBy !== "referral_date") p.set("sort_by", filters.sortBy);
  if (filters.sortDir !== "DESC") p.set("sort_dir", filters.sortDir);
  if (filters.page !== 1) p.set("page", String(filters.page));
  if (filters.pageSize !== 25) p.set("page_size", String(filters.pageSize));
  return p;
}

/** Deserialise URLSearchParams back to filter state. */
export function deserialiseFilters(params: URLSearchParams): MissionControlFilters {
  const pathwayFilter = params.get("pathway_filter");
  const reviewStatus = params.get("review_status");
  const sortDir = params.get("sort_dir");

  return {
    dateFrom: params.get("date_from") ?? "",
    dateTo: params.get("date_to") ?? "",
    orgId: params.get("org_id") ?? "",
    patientId: params.get("patient_id") ?? "",
    pathwayFilter:
      pathwayFilter === "confirmed" || pathwayFilter === "closures"
        ? pathwayFilter
        : "all",
    cancerTypes: params.get("cancer_types")
      ? params.get("cancer_types")!.split(",").filter(Boolean)
      : [],
    closureReasons: params.get("closure_reasons")
      ? params.get("closure_reasons")!.split(",").filter(Boolean)
      : [],
    reviewStatus:
      reviewStatus === "reviewed" || reviewStatus === "unreviewed"
        ? reviewStatus
        : "all",
    sortBy: params.get("sort_by") ?? "referral_date",
    sortDir: sortDir === "ASC" ? "ASC" : "DESC",
    page: parseInt(params.get("page") ?? "1", 10) || 1,
    pageSize: parseInt(params.get("page_size") ?? "25", 10) || 25,
  };
}

/** Build the query string for the backend API from filter state. */
export function toApiParams(filters: MissionControlFilters): URLSearchParams {
  const p = new URLSearchParams();
  if (filters.dateFrom) p.set("date_from", filters.dateFrom);
  if (filters.dateTo) p.set("date_to", filters.dateTo);
  if (filters.orgId) p.set("org_id", filters.orgId);
  const pid = filters.patientId.trim();
  if (pid) p.set("patient_id", pid);
  p.set("pathway_filter", filters.pathwayFilter);
  if (filters.cancerTypes.length) p.set("cancer_types", filters.cancerTypes.join(","));
  if (filters.closureReasons.length) p.set("closure_reasons", filters.closureReasons.join(","));
  p.set("review_status", filters.reviewStatus);
  p.set("sort_by", filters.sortBy);
  p.set("sort_dir", filters.sortDir);
  return p;
}
