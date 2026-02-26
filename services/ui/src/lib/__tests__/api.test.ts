import {
  fetchPatients,
  fetchPatient,
  fetchPatientEncounters,
  fetchEncounter,
  fetchEncounterCodedLinks,
  addCodedLink,
  deleteCodedLink,
  recodeCodedLink,
  updateCodedLinkModifiers,
  resetPatient,
  resetReviewQueue,
  syncGoldToPatient,
  exportMedSpaCyTraining,
  inferEncounter,
  fetchTasks,
  fetchTaskDetail,
  submitDecision,
  submitGameScore,
  fetchLeaderboard,
  searchPatientEncounters,
  searchTerms,
} from "../api";

const BASE = "http://localhost:8000";

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

// ── Error handling ──

describe("fetchJson error handling", () => {
  it("throws custom detail from server", async () => {
    mockFetchError(400, "Bad patient ID");
    await expect(fetchPatients()).rejects.toThrow("Bad patient ID");
  });

  it("throws default 404 message when no detail", async () => {
    mockFetchError(404);
    await expect(fetchPatients()).rejects.toThrow(
      "Not found. Check the ID or return to the list.",
    );
  });

  it("throws default 500 message when no detail", async () => {
    mockFetchError(500);
    await expect(fetchPatients()).rejects.toThrow(
      "Server error. Try again or contact support.",
    );
  });

  it("throws generic message for other status codes", async () => {
    mockFetchError(403);
    await expect(fetchPatients()).rejects.toThrow(
      "Request failed. Please try again.",
    );
  });

  it("handles non-JSON error body gracefully", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: () => Promise.reject(new Error("not json")),
    });
    await expect(fetchPatients()).rejects.toThrow(
      "Server error. Try again or contact support.",
    );
  });
});

// ── GET requests ──

describe("GET API functions", () => {
  it("fetchPatients calls /patients", async () => {
    mockFetchOk([{ patient_id: "P1", encounter_count: 3 }]);
    const result = await fetchPatients();
    expect(global.fetch).toHaveBeenCalledWith(`${BASE}/patients`, undefined);
    expect(result).toEqual([{ patient_id: "P1", encounter_count: 3 }]);
  });

  it("fetchPatient calls /patients/:id", async () => {
    mockFetchOk({ patient_id: "P1", encounter_count: 5 });
    await fetchPatient("P1");
    expect(global.fetch).toHaveBeenCalledWith(`${BASE}/patients/P1`, undefined);
  });

  it("fetchPatientEncounters includes limit param", async () => {
    mockFetchOk([]);
    await fetchPatientEncounters("P1", 100);
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/patients/P1/encounters?limit=100`,
      undefined,
    );
  });

  it("fetchPatientEncounters defaults limit to 500", async () => {
    mockFetchOk([]);
    await fetchPatientEncounters("P1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/patients/P1/encounters?limit=500`,
      undefined,
    );
  });

  it("fetchEncounter calls correct URL", async () => {
    mockFetchOk({ encounter_id: "E1", date: "2025-01-01", text: "hi", coded_count: 0 });
    await fetchEncounter("P1", "E1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/patients/P1/encounters/E1`,
      undefined,
    );
  });

  it("fetchEncounterCodedLinks calls correct URL", async () => {
    mockFetchOk([]);
    await fetchEncounterCodedLinks("P1", "E1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/patients/P1/encounters/E1/coded-links`,
      undefined,
    );
  });

  it("fetchTaskDetail calls correct URL", async () => {
    mockFetchOk({ task: {}, candidate: {} });
    await fetchTaskDetail("T1");
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/review/tasks/T1`,
      undefined,
    );
  });

  it("fetchTasks builds query string with all params", async () => {
    mockFetchOk([]);
    await fetchTasks("pending", "P1", 10);
    const url = (global.fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("status=pending");
    expect(url).toContain("patient_id=P1");
    expect(url).toContain("limit=10");
  });

  it("fetchTasks omits null params", async () => {
    mockFetchOk([]);
    await fetchTasks(null, null, 20);
    const url = (global.fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).not.toContain("status=");
    expect(url).not.toContain("patient_id=");
    expect(url).toContain("limit=20");
  });

  it("fetchLeaderboard passes game and limit", async () => {
    mockFetchOk([]);
    await fetchLeaderboard("snake", 5);
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/games/leaderboard?game=snake&limit=5`,
      undefined,
    );
  });

  it("searchPatientEncounters builds correct params", async () => {
    mockFetchOk([]);
    await searchPatientEncounters("P1", "cough", "semantic", 25);
    const url = (global.fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("/patients/P1/encounters/search?");
    expect(url).toContain("q=cough");
    expect(url).toContain("mode=semantic");
    expect(url).toContain("limit=25");
  });

  it("searchTerms encodes query and passes limit", async () => {
    mockFetchOk([]);
    await searchTerms("chest pain", 10);
    const url = (global.fetch as jest.Mock).mock.calls[0][0] as string;
    expect(url).toContain("q=chest%20pain");
    expect(url).toContain("limit=10");
  });
});

// ── POST / DELETE / PATCH / PUT requests ──

describe("mutation API functions", () => {
  it("addCodedLink sends POST with JSON body", async () => {
    const body = { concept_id: "12345", term: "Cough" };
    mockFetchOk({ added: true, concept_id: "12345" });
    await addCodedLink("P1", "E1", body);
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/encounters/E1/coded-links`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(body);
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("deleteCodedLink sends DELETE", async () => {
    mockFetchOk({ deleted: true });
    await deleteCodedLink("P1", "E1", "C1");
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/encounters/E1/coded-links/C1`);
    expect(init.method).toBe("DELETE");
  });

  it("recodeCodedLink sends PATCH with body", async () => {
    const body = { new_concept_id: "99999", term: "Fever" };
    mockFetchOk({ recode: true, new_concept_id: "99999" });
    await recodeCodedLink("P1", "E1", "C1", body);
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/encounters/E1/coded-links/C1`);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual(body);
  });

  it("updateCodedLinkModifiers sends PUT", async () => {
    const mods = { value: "120", unit: "mmHg" };
    mockFetchOk({ concept_id: "C1", modifiers: mods });
    await updateCodedLinkModifiers("P1", "E1", "C1", mods);
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/encounters/E1/coded-links/C1/modifiers`);
    expect(init.method).toBe("PUT");
  });

  it("resetPatient sends POST", async () => {
    mockFetchOk({ patient_id: "P1", links_deleted: 5 });
    await resetPatient("P1");
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/reset`);
    expect(init.method).toBe("POST");
  });

  it("resetReviewQueue sends POST", async () => {
    mockFetchOk({ patient_id: "P1", deleted: 3 });
    await resetReviewQueue("P1");
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/reset-review-queue`);
    expect(init.method).toBe("POST");
  });

  it("syncGoldToPatient sends POST", async () => {
    mockFetchOk({ patient_id: "P1", encounters_synced: 2, links_created: 10 });
    await syncGoldToPatient("P1");
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/patients/P1/sync-gold`);
    expect(init.method).toBe("POST");
  });

  it("exportMedSpaCyTraining sends POST with body", async () => {
    mockFetchOk({ export_id: "X1", entity_count: 10, kb_count: 5, encounter_count: 3 });
    await exportMedSpaCyTraining({ export_name: "test", patient_ids: ["P1"] });
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/exports/medspacy-training`);
    expect(JSON.parse(init.body)).toEqual({ export_name: "test", patient_ids: ["P1"] });
  });

  it("inferEncounter sends dry_run flag", async () => {
    mockFetchOk({ encounter_id: "E1", entities: [], written: false });
    await inferEncounter("P1", "E1", false);
    const [, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ dry_run: false });
  });

  it("submitDecision sends POST with decision body", async () => {
    const body = { action: "approve", reviewer: "user1", reason: "Looks good" };
    mockFetchOk({ task_id: "T1", candidate_id: "C1", status: "approved", approval_event_id: "AE1" });
    await submitDecision("T1", body);
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/review/tasks/T1/decision`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual(body);
  });

  it("submitGameScore sends POST with score body", async () => {
    const body = { game: "snake" as const, player: "Alice", score: 100, level: 3 };
    mockFetchOk({ id: "S1", ...body, created_at: "", rank: 1 });
    await submitGameScore(body);
    const [url, init] = (global.fetch as jest.Mock).mock.calls[0];
    expect(url).toBe(`${BASE}/games/scores`);
    expect(JSON.parse(init.body)).toEqual(body);
  });
});
