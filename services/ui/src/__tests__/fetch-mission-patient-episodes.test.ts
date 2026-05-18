// VT-DAEE0DFD -- fetchMissionPatientEpisodes hits the dedicated
// per-patient endpoint that returns every EpisodeOfCare regardless
// of the dashboard cohort filter (DI-5E47FA5D).

import { fetchMissionPatientEpisodes } from "@/lib/missionControlApi";

describe("fetchMissionPatientEpisodes", () => {
  const originalFetch = global.fetch;

  afterEach(() => {
    global.fetch = originalFetch;
    jest.resetAllMocks();
  });

  function mockFetchOk(body: unknown) {
    const fn = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => body,
    } as unknown as Response);
    global.fetch = fn as unknown as typeof fetch;
    return fn;
  }

  it("calls the patient-scoped episodes endpoint with the patient id in the path", async () => {
    const fetchMock = mockFetchOk({
      patient_id: "9990001006",
      episodes: [],
    });
    await fetchMissionPatientEpisodes("9990001006");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toMatch(
      /\/api\/proxy\/analytics\/mission-control\/patients\/9990001006\/episodes$/,
    );
  });

  it("URL-encodes the patient id", async () => {
    const fetchMock = mockFetchOk({ patient_id: "id with space", episodes: [] });
    await fetchMissionPatientEpisodes("id with space");
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toMatch(/\/patients\/id%20with%20space\/episodes/);
  });

  it("appends ?org_id=... when an orgId is supplied", async () => {
    const fetchMock = mockFetchOk({ patient_id: "p1", episodes: [] });
    await fetchMissionPatientEpisodes("p1", { orgId: "org-1" });
    const calledUrl = String(fetchMock.mock.calls[0][0]);
    expect(calledUrl).toMatch(/\/patients\/p1\/episodes\?org_id=org-1$/);
  });

  it("returns the parsed body verbatim", async () => {
    mockFetchOk({
      patient_id: "p1",
      episodes: [
        { episode_id: "ep-A", status: "in_review" },
        { episode_id: "ep-B", status: "confirmed_cancer" },
      ],
    });
    const res = await fetchMissionPatientEpisodes("p1");
    expect(res.patient_id).toBe("p1");
    expect(res.episodes).toHaveLength(2);
    expect(res.episodes.map((e) => e.status)).toEqual([
      "in_review",
      "confirmed_cancer",
    ]);
  });

  it("propagates a 404 from the backend as a thrown Error", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "Patient not found" }),
    } as unknown as Response) as unknown as typeof fetch;
    await expect(fetchMissionPatientEpisodes("nope")).rejects.toThrow(
      /Patient not found/,
    );
  });
});
