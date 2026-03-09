import {
  fetchEpisodeSummary,
  fetchEpisodeTimeline,
  fetchSafetyNetAlerts,
  fetchPatientCCI,
  fetchKPIBenchmarks,
  fetchKPITrends,
  fetchIMDData,
  fetchMeasures,
  evaluateMeasure,
} from "../analyticsApi";

const PROXY = "http://localhost/api/proxy";
const ANALYTICS = PROXY;
const FHIR = PROXY;
const REQUEST_OPTIONS = {
  credentials: "include" as RequestCredentials,
  headers: { "X-Requested-With": "XMLHttpRequest" },
};

function mockFetchOk(data: unknown) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok: true,
    json: () => Promise.resolve(data),
  });
}

function mockFetchError(status: number, detail?: string) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve(detail ? { detail } : {}),
  });
}

describe("Analytics API — episodes", () => {
  it("fetchEpisodeSummary hits correct endpoint", async () => {
    mockFetchOk([]);
    await fetchEpisodeSummary();
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/episodes/summary`,
      REQUEST_OPTIONS,
    );
  });

  it("fetchEpisodeSummary passes orgId", async () => {
    mockFetchOk([]);
    await fetchEpisodeSummary("ORG1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/episodes/summary?org_id=ORG1`,
      REQUEST_OPTIONS,
    );
  });

  it("fetchEpisodeTimeline with no params", async () => {
    mockFetchOk([]);
    await fetchEpisodeTimeline();
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/episodes/timeline`,
      REQUEST_OPTIONS,
    );
  });

  it("fetchEpisodeTimeline with both params", async () => {
    mockFetchOk([]);
    await fetchEpisodeTimeline("P1", "ORG1");
    const url = (global.fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("patient_id=P1");
    expect(url).toContain("org_id=ORG1");
  });

  it("fetchSafetyNetAlerts with orgId", async () => {
    mockFetchOk([]);
    await fetchSafetyNetAlerts("ORG1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/safety-netting/alerts?org_id=ORG1`,
      REQUEST_OPTIONS,
    );
  });
});

describe("Analytics API — CCI", () => {
  it("fetchPatientCCI calls correct URL", async () => {
    mockFetchOk({ patient_id: "P1", cci_score: 4, matched_conditions: [] });
    const result = await fetchPatientCCI("P1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/cci/P1`,
      REQUEST_OPTIONS,
    );
    expect(result.cci_score).toBe(4);
  });
});

describe("Analytics API — benchmarks", () => {
  it("fetchKPIBenchmarks with no orgId", async () => {
    mockFetchOk([]);
    await fetchKPIBenchmarks();
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/benchmarks/kpis`,
      REQUEST_OPTIONS,
    );
  });

  it("fetchKPIBenchmarks with orgId", async () => {
    mockFetchOk([]);
    await fetchKPIBenchmarks("ORG1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/benchmarks/kpis?org_id=ORG1`,
      REQUEST_OPTIONS,
    );
  });

  it("fetchKPITrends builds query string", async () => {
    mockFetchOk([]);
    await fetchKPITrends("days_to_referral", "ORG1");
    const url = (global.fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("metric=days_to_referral");
    expect(url).toContain("org_id=ORG1");
  });

  it("fetchKPITrends with no params hits bare URL", async () => {
    mockFetchOk([]);
    await fetchKPITrends();
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/benchmarks/trends`,
      REQUEST_OPTIONS,
    );
  });
});

describe("Analytics API — IMD", () => {
  it("fetchIMDData encodes postcode", async () => {
    mockFetchOk({ imd_rank: "5000" });
    await fetchIMDData("SW1A 1AA");
    expect(global.fetch).toHaveBeenCalledWith(
      `${ANALYTICS}/analytics/imd/SW1A%201AA`,
      REQUEST_OPTIONS,
    );
  });
});

describe("FHIR API — measures", () => {
  it("fetchMeasures with no name", async () => {
    mockFetchOk({ resourceType: "Bundle", type: "searchset", total: 0, entry: [] });
    await fetchMeasures();
    expect(global.fetch).toHaveBeenCalledWith(
      `${FHIR}/fhir/Measure`,
      REQUEST_OPTIONS,
    );
  });

  it("fetchMeasures with name filter", async () => {
    mockFetchOk({ resourceType: "Bundle", type: "searchset", total: 1, entry: [] });
    await fetchMeasures("encounter-count");
    expect(global.fetch).toHaveBeenCalledWith(
      `${FHIR}/fhir/Measure?name=encounter-count`,
      REQUEST_OPTIONS,
    );
  });

  it("evaluateMeasure calls $evaluate-measure", async () => {
    mockFetchOk({ resourceType: "MeasureReport" });
    await evaluateMeasure("M1", "ORG1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${FHIR}/fhir/Measure/M1/$evaluate-measure?org_id=ORG1`,
      REQUEST_OPTIONS,
    );
  });

  it("evaluateMeasure without orgId", async () => {
    mockFetchOk({ resourceType: "MeasureReport" });
    await evaluateMeasure("M1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${FHIR}/fhir/Measure/M1/$evaluate-measure`,
      REQUEST_OPTIONS,
    );
  });
});

describe("Analytics API error handling", () => {
  it("throws detail from analytics error response", async () => {
    mockFetchError(500, "Internal analytics error");
    await expect(fetchEpisodeSummary()).rejects.toThrow("Internal analytics error");
  });

  it("throws generic message when no detail", async () => {
    mockFetchError(400);
    await expect(fetchPatientCCI("P1")).rejects.toThrow("Request failed (400)");
  });
});
