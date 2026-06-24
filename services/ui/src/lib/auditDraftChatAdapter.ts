/**
 * Chat adapter for the Audit Draft AI assistant.
 *
 * Sends the multi-turn conversation to the SSE endpoint and parses the
 * streamed events into text deltas and structured tile suggestions.
 *
 * Atlas trace:
 *   DO: DO-3775670C
 *   DI: DI-64CA7740
 */

export interface DraftMessage {
  role: "user" | "assistant";
  content: string;
}

export interface TileSuggestion {
  metric_id: string;
  label: string;
  tile_type: string;
  section?: string;
}

export interface SendMessageOptions {
  userText: string;
  history: DraftMessage[];
  currentTiles: { metric_id: string; label: string }[];
  existingMetricIds?: string[];
  onText: (delta: string) => void;
  onTiles: (tiles: TileSuggestion[]) => void;
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
 * Send a user message and stream the AI response.
 *
 * The function returns a promise that resolves when the stream finishes
 * or the abort signal fires. Callers must await it if they need to know
 * when the stream is done.
 */
export async function sendMessage(opts: SendMessageOptions): Promise<void> {
  const {
    userText,
    history,
    currentTiles,
    existingMetricIds = [],
    onText,
    onTiles,
    onFinish,
    onError,
    signal,
  } = opts;

  const messages: DraftMessage[] = [
    ...history,
    { role: "user", content: userText },
  ];

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
          onText((event.delta as string) ?? "");
        } else if (type === "tool-input-available") {
          const input = (event.input as Record<string, unknown>) ?? {};
          const tiles = (input.tiles as TileSuggestion[]) ?? [];
          if (tiles.length > 0) onTiles(tiles);
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
