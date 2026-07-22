/**
 * LEO widget release loader.
 *
 * Atlas trace:
 *   DO: DO-3B62F38E
 *   DI: DI-3C06AFD0
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-3B62F38E")
 *
 * Selects the active build from /v1/manifest.json. The host pins a
 * major version (e.g. major=1) and the loader returns the active
 * patch+minor inside that major. CSO rollback is achieved by
 * publishing a different active hash inside the same major; the
 * loader picks it up on the next poll because the response is
 * cache-controlled with max-age <= 60s.
 */

export interface Manifest {
  major: number;
  active: string;
  released_at?: string;
  notes?: string;
}

export interface FetchActiveBuildArgs {
  manifestUrl: string;
  pinnedMajor: string;
  fetcher?: typeof fetch;
}

function _normaliseMajor(value: number | string): string {
  const text = String(value);
  // split(".") on any string always yields at least one element; the
  // fallback only satisfies noUncheckedIndexedAccess, it is never hit.
  return text.split(".")[0] ?? text;
}

export async function fetchActiveBuild(
  args: FetchActiveBuildArgs,
): Promise<string> {
  const fetcher = args.fetcher ?? globalThis.fetch?.bind(globalThis);
  if (!fetcher) {
    throw new Error("leo-widget: no fetch implementation available");
  }
  const response = await fetcher(args.manifestUrl, {
    method: "GET",
    headers: { Accept: "application/json" },
    credentials: "omit",
    mode: "cors",
  });
  if (!response.ok) {
    throw new Error(
      `leo-widget: manifest fetch failed (${response.status} ${response.statusText})`,
    );
  }
  const body = (await response.json()) as Manifest;
  if (
    !body ||
    typeof body.active !== "string" ||
    typeof body.major !== "number"
  ) {
    throw new Error("leo-widget: manifest is missing active / major fields");
  }
  if (_normaliseMajor(body.major) !== _normaliseMajor(args.pinnedMajor)) {
    throw new Error(
      `leo-widget: refusing to load build ${body.active} (major ${body.major}) ` +
        `against pinned major ${args.pinnedMajor}`,
    );
  }
  const activeMajor = body.active.split(".")[0] ?? body.active;
  if (_normaliseMajor(activeMajor) !== _normaliseMajor(args.pinnedMajor)) {
    throw new Error(
      `leo-widget: manifest active build ${body.active} does not start with pinned major ${args.pinnedMajor}`,
    );
  }
  return body.active;
}
