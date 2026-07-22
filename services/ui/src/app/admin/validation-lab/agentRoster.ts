/**
 * Friendly agent names for Validation Lab pipeline workers.
 *
 * Atlas: DI-FE423B8D / DO-158BE606
 *
 * Local start scripts assign PIPELINE_WORKER_NAME from this roster.
 * The UI also maps unknown worker ids onto the same names so older
 * runs still read as named agents instead of a bare "worker" label.
 */

export const PIPELINE_AGENT_ROSTER = [
  "Ada",
  "Curie",
  "Nightingale",
  "Faraday",
  "Turing",
  "Lovelace",
  "Pasteur",
  "Jenner",
  "Hodgkin",
  "Seacole",
  "Fleming",
  "Darwin",
] as const;

function hashSeed(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return h;
}

/** Host / replica prefix before the delivery id. */
export function workerHostPrefix(workerId: string): string {
  const raw = (workerId || "").trim();
  if (!raw) return "";
  return raw.split(":")[0] || raw;
}

/**
 * Friendly agent label for a lease_owner / completed_by worker id.
 * Prefers an explicit roster name on the host prefix; otherwise hashes
 * the id onto the roster so generic "worker:..." ids still look distinct.
 */
export function formatAgentName(workerId: string): string {
  const raw = (workerId || "").trim();
  if (!raw) return "";
  const host = workerHostPrefix(raw);
  const known = PIPELINE_AGENT_ROSTER.find(
    (name) => name.toLowerCase() === host.toLowerCase(),
  );
  if (known) return known;
  const seed =
    !host || host.toLowerCase() === "worker" || host.startsWith("worker-")
      ? raw
      : host;
  const idx = hashSeed(seed) % PIPELINE_AGENT_ROSTER.length;
  return PIPELINE_AGENT_ROSTER[idx];
}
