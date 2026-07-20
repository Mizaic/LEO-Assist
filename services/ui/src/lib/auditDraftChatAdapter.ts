/**
 * Chat adapter for the Audit Draft AI assistant -- multi-phase flow.
 *
 * Phases:
 *   intent    -- user sends initial request; backend returns questions-available
 *   discover  -- user submits answers; backend returns plan-available
 *   build     -- frontend sends approved tiles; backend validates and adds them
 *
 * Atlas trace:
 *   DO: DO-3775670C
 *   DI: DI-64CA7740
 */

export interface DraftMessage {
  role: "user" | "assistant";
  content: string;
}

// -- Discovery phase ---------------------------------------------------------

export interface DiscoveryOption {
  id: string;
  label: string;
  recommended: boolean;
}

export interface DiscoveryQuestion {
  id: string;
  question: string;
  options: DiscoveryOption[];
}

export interface GatherRequirementsResult {
  intent_summary: string;
  questions: DiscoveryQuestion[];
}

// -- Planning phase ----------------------------------------------------------

export interface PlannedPage {
  page_id: string;
  label: string;
  kind?: "snapshot" | "report";
}

export interface PlannedTile {
  metric_id: string;
  label: string;
  tile_type: string;
  section?: string;
  page_id?: string;
  reason: string;
  story_headline?: string;
  highlight_key?: string;
}

export interface DashboardPlan {
  rationale: string;
  tiles: PlannedTile[];
  pages?: PlannedPage[];
  zone1_narrative?: string;
  zone2_narrative?: string;
  warnings: string[];
}

// -- Build phase -------------------------------------------------------------

export interface SkippedTile {
  metric_id: string;
  reason: string;
}

export interface BuildSummary {
  added: number;
  skipped: SkippedTile[];
  warnings: string[];
}

// -- Adapter options ---------------------------------------------------------

export type AssistantPhaseRequest = "intent" | "discover" | "build";

export interface SendMessageOptions {
  /** Current phase determines which SSE events are expected. */
  phase: AssistantPhaseRequest;
  /** User-typed text (not used in build phase). */
  userText?: string;
  /** Full conversation history. */
  history: DraftMessage[];
  /** Answers from discovery MCQs: question_id -> option_id */
  answers?: Record<string, string>;
  /** Approved tiles to add (build phase only). */
  approvedTiles?: PlannedTile[];
  /** Approved pages from the plan (build phase). */
  approvedPages?: PlannedPage[];
  zone1Narrative?: string;
  zone2Narrative?: string;
  /** Tiles already on the grid. */
  currentTiles?: { metric_id: string; label: string }[];
  existingMetricIds?: string[];
  /** Streaming callbacks. */
  onText?: (delta: string) => void;
  onQuestions?: (result: GatherRequirementsResult) => void;
  onPlan?: (plan: DashboardPlan) => void;
  onPagesProposed?: (pages: PlannedPage[]) => void;
  onNarrativesProposed?: (zone1: string, zone2: string) => void;
  onTileAdded?: (tile: PlannedTile) => void;
  onBuildComplete?: (summary: BuildSummary) => void;
  onFinish: () => void;
  onError: (message: string) => void;
  signal?: AbortSignal;
}

function parseSseLine(line: string): Record<string, unknown> | null {
  if (!line.startsWith("data: ")) return null;
  try {
    return JSON.parse(line.slice(6)) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Send a request for the current phase and stream the AI response.
 */
export async function sendMessage(opts: SendMessageOptions): Promise<void> {
  const {
    phase,
    userText,
    history,
    answers = {},
    approvedTiles = [],
    approvedPages = [],
    zone1Narrative = "",
    zone2Narrative = "",
    currentTiles = [],
    existingMetricIds = [],
    onText,
    onQuestions,
    onPlan,
    onPagesProposed,
    onNarrativesProposed,
    onTileAdded,
    onBuildComplete,
    onFinish,
    onError,
    signal,
  } = opts;

  const messages: DraftMessage[] =
    phase !== "build" && userText
      ? [...history, { role: "user", content: userText }]
      : [...history];

  let response: Response;
  try {
    response = await fetch("/api/audit-draft", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({
        messages,
        phase,
        answers,
        approved_tiles: approvedTiles,
        approved_pages: approvedPages,
        zone1_narrative: zone1Narrative,
        zone2_narrative: zone2Narrative,
        current_tiles: currentTiles,
        existing_metric_ids: existingMetricIds,
      }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      onError(err instanceof Error ? err.message : "Request failed");
    }
    return;
  }

  if (!response.ok || !response.body) {
    onError(`Server error: ${response.status}`);
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        const event = parseSseLine(line.trim());
        if (!event) continue;

        const type = event.type as string;

        if (type === "text-delta") {
          onText?.((event.delta as string) ?? "");
        } else if (type === "questions-available") {
          const input = (event.input as Record<string, unknown>) ?? {};
          onQuestions?.(input as unknown as GatherRequirementsResult);
        } else if (type === "plan-available") {
          const input = (event.input as Record<string, unknown>) ?? {};
          onPlan?.(input as unknown as DashboardPlan);
        } else if (type === "pages-proposed") {
          onPagesProposed?.((event.pages as PlannedPage[]) ?? []);
        } else if (type === "narratives-proposed") {
          onNarrativesProposed?.(
            (event.zone1_narrative as string) ?? "",
            (event.zone2_narrative as string) ?? "",
          );
        } else if (type === "tile-added") {
          const tile = event.tile as PlannedTile;
          if (tile) onTileAdded?.(tile);
        } else if (type === "build-complete") {
          onBuildComplete?.(event as unknown as BuildSummary);
        } else if (type === "finish") {
          onFinish();
        } else if (type === "error") {
          onError((event.message as string) ?? "Unknown error");
        }
      }
    }
  } catch (err) {
    if ((err as Error).name !== "AbortError") {
      onError(err instanceof Error ? err.message : "Stream read failed");
    }
  } finally {
    reader.releaseLock();
  }
}
