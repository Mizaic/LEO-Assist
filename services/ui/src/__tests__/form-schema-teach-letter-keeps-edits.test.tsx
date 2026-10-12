/**
 * Teach dialog: loading the sample letter after editing keeps the edits.
 *
 * Saving needs the letter the form was taught from, so a reviewer who
 * opens a saved form often loads the letter after making changes. The
 * editor must not reload the saved form and throw those changes away.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
import { act, renderHook, waitFor } from "@testing-library/react";

import { useFormSchemaTeach } from "../components/operations/useFormSchemaTeach";

const SAVED_SCHEMA = {
  form_name: "Lower GI",
  fingerprint: "abcdef0123456789",
  sections: [
    {
      section_id: "fit_result",
      section_type: "free_text",
      label: "FIT result",
      start_pattern: "Faecal Immunochemical",
      items: [],
    },
  ],
  completeness_groups: [],
};

function jsonResponse(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response;
}

let fetchMock: jest.Mock;

beforeEach(() => {
  fetchMock = jest.fn(async (url: string) => {
    if (String(url).startsWith("/api/form-schemas/abcdef0123456789")) {
      return jsonResponse({ schema: SAVED_SCHEMA, match: "fingerprint" });
    }
    return jsonResponse({ sections: [], detection: {} });
  });
  global.fetch = fetchMock as unknown as typeof fetch;
});

function schemaLoads(): number {
  return fetchMock.mock.calls.filter(([url, init]) =>
    String(url).startsWith("/api/form-schemas/abcdef0123456789") && !init?.method,
  ).length;
}

test("loading the letter after editing a saved form keeps the edits", async () => {
  const { result, rerender } = renderHook(
    ({ letter }) => useFormSchemaTeach("abcdef0123456789", letter, "Lower GI"),
    { initialProps: { letter: "" } },
  );
  await waitFor(() => expect(result.current.loading).toBe(false));
  act(() => result.current.patchSection(0, { label: "FIT result (edited)" }));

  rerender({ letter: "Faecal Immunochemical test result ug/g > 200 ug/g" });

  await waitFor(() => expect(result.current.loading).toBe(false));
  expect(result.current.sections[0]?.label).toBe("FIT result (edited)");
  expect(schemaLoads()).toBe(1);
});

test("a letter that arrives before a new form has any sections is still read", async () => {
  const detected = { ...SAVED_SCHEMA.sections[0], label: "Detected FIT result" };
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith("/detect")) {
      const text = JSON.parse(String(init?.body)).text as string;
      return jsonResponse({ sections: text ? [detected] : [], detection: {} });
    }
    return jsonResponse({ schema: null, match: "none" });
  });
  const { result, rerender } = renderHook(
    ({ letter }) => useFormSchemaTeach("abcdef0123456789", letter, "Lower GI"),
    { initialProps: { letter: "" } },
  );
  await waitFor(() => expect(result.current.loading).toBe(false));

  rerender({ letter: "Faecal Immunochemical test result ug/g > 200 ug/g" });

  await waitFor(() =>
    expect(result.current.sections[0]?.label).toBe("Detected FIT result"),
  );
});
