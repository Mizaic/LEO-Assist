/**
 * Tests for domain/subdomain API client functions.
 */

import {
  fetchDomains,
  fetchDomain,
  createDomain,
  deleteDomain,
  createSubdomain,
  fetchSubdomain,
  addConceptToSubdomain,
  removeConceptFromSubdomain,
  updateSubdomain,
} from "../analyticsApi";

const mockFetch = jest.fn();
global.fetch = mockFetch;

function ok(body: unknown, status = 200) {
  return {
    ok: true,
    status,
    json: () => Promise.resolve(body),
  };
}

function err(detail: string, status = 400) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({ detail }),
  };
}

beforeEach(() => mockFetch.mockReset());

describe("fetchDomains", () => {
  it("returns domain list", async () => {
    const data = [
      { id: "cancer_audit", name: "Cancer Audit", description: "", subdomain_count: 3 },
    ];
    mockFetch.mockResolvedValue(ok(data));

    const result = await fetchDomains();
    expect(result).toEqual(data);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/domains"),
      undefined,
    );
  });
});

describe("fetchDomain", () => {
  it("fetches domain detail with subdomains", async () => {
    const data = {
      id: "cancer_audit",
      name: "Cancer Audit",
      description: "",
      subdomain_count: 1,
      subdomains: [
        { name: "cancer_types", description: "", concept_count: 5, semantic_tags: [] },
      ],
    };
    mockFetch.mockResolvedValue(ok(data));

    const result = await fetchDomain("cancer_audit");
    expect(result.subdomains).toHaveLength(1);
    expect(result.subdomains[0].name).toBe("cancer_types");
  });
});

describe("createDomain", () => {
  it("posts with name and description", async () => {
    mockFetch.mockResolvedValue(ok({ id: "qof", name: "QOF", description: "Quality", subdomain_count: 0 }));

    const result = await createDomain("QOF", "Quality");
    expect(result.id).toBe("qof");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/domains"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "QOF", description: "Quality" }),
      }),
    );
  });
});

describe("deleteDomain", () => {
  it("sends DELETE request", async () => {
    mockFetch.mockResolvedValue({ ok: true, status: 204 });

    await deleteDomain("test_audit");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/domains/test_audit"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("createSubdomain", () => {
  it("creates subdomain under domain", async () => {
    mockFetch.mockResolvedValue(ok({
      name: "referrals",
      description: "Referral procedures",
      concept_count: 0,
      semantic_tags: [],
    }));

    const result = await createSubdomain("cancer_audit", "referrals", {
      description: "Referral procedures",
    });
    expect(result.name).toBe("referrals");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/analytics/domains/cancer_audit/subdomains"),
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("fetchSubdomain", () => {
  it("returns subdomain with concepts", async () => {
    const data = {
      name: "cancer_types",
      description: "",
      concept_count: 1,
      semantic_tags: [],
      concepts: [{ concept_id: 254837009, term: "Breast cancer" }],
    };
    mockFetch.mockResolvedValue(ok(data));

    const result = await fetchSubdomain("cancer_audit", "cancer_types");
    expect(result.concepts).toHaveLength(1);
    expect(result.concepts[0].concept_id).toBe(254837009);
  });
});

describe("addConceptToSubdomain", () => {
  it("posts concept with synonyms", async () => {
    mockFetch.mockResolvedValue(ok({
      name: "cancer_types",
      concept_count: 1,
      concepts: [{ concept_id: 254837009, term: "Breast cancer" }],
    }));

    await addConceptToSubdomain(
      "cancer_audit",
      "cancer_types",
      254837009,
      "Breast cancer",
      ["breast carcinoma"],
    );

    const body = JSON.parse(mockFetch.mock.calls[0][1].body);
    expect(body.concept_id).toBe(254837009);
    expect(body.synonyms).toEqual(["breast carcinoma"]);
  });
});

describe("removeConceptFromSubdomain", () => {
  it("sends DELETE to concept endpoint", async () => {
    mockFetch.mockResolvedValue(ok({
      name: "cancer_types",
      concept_count: 0,
      concepts: [],
    }));

    await removeConceptFromSubdomain("cancer_audit", "cancer_types", 254837009);
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/cancer_types/concepts/254837009"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("updateSubdomain", () => {
  it("sends PUT with partial update", async () => {
    mockFetch.mockResolvedValue(ok({
      name: "cancer_types",
      description: "Updated",
      concept_count: 0,
      semantic_tags: ["Disease"],
    }));

    const result = await updateSubdomain("cancer_audit", "cancer_types", {
      description: "Updated",
      semantic_tags: ["Disease"],
    });
    expect(result.description).toBe("Updated");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/cancer_audit/subdomains/cancer_types"),
      expect.objectContaining({ method: "PUT" }),
    );
  });
});
