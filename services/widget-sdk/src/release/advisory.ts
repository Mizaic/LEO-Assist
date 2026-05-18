/**
 * AdvisoryClient - non-dismissible LEO Clinical Safety Officer banner.
 *
 * Atlas trace:
 *   DO: DO-3B62F38E
 *   DI: DI-3C06AFD0
 *   Risk mitigated: R-4965BCD2 (CSO override channel for hazards
 *     discovered post-deployment)
 *
 * The advisory banner is rendered into the widget trust boundary
 * by the consumer. AdvisoryClient deliberately exposes NO method
 * named hide / dismiss / disable / suppress: a published advisory
 * stays visible until the CSO clears it at the source.
 */

export interface Advisory {
  active: boolean;
  severity?: "info" | "safety" | "critical";
  headline?: string;
  body?: string;
  published_at?: string;
}

export interface AdvisoryClientOptions {
  advisoryUrl: string;
  container: HTMLElement;
  fetcher?: typeof fetch;
  pollIntervalMs?: number;
}

export class AdvisoryClient {
  private readonly _advisoryUrl: string;
  private readonly _container: HTMLElement;
  private readonly _fetchImpl: typeof fetch;
  private readonly _pollIntervalMs: number;
  private _timer: ReturnType<typeof setInterval> | null = null;

  constructor(options: AdvisoryClientOptions) {
    if (!options.advisoryUrl) {
      throw new Error("leo-widget: advisoryUrl is required");
    }
    if (!options.container) {
      throw new Error("leo-widget: advisory container is required");
    }
    this._advisoryUrl = options.advisoryUrl;
    this._container = options.container;
    this._fetchImpl =
      options.fetcher ?? globalThis.fetch?.bind(globalThis);
    this._pollIntervalMs = options.pollIntervalMs ?? 60_000;
  }

  start(): void {
    void this.refresh();
    if (this._timer === null) {
      this._timer = setInterval(() => {
        void this.refresh();
      }, this._pollIntervalMs);
    }
  }

  stop(): void {
    // stop only halts the poll loop; an already-rendered banner
    // stays in the DOM. There is no API to remove it.
    if (this._timer !== null) {
      clearInterval(this._timer);
      this._timer = null;
    }
  }

  async refresh(): Promise<Advisory | null> {
    try {
      const response = await this._fetchImpl(this._advisoryUrl, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "omit",
        mode: "cors",
      });
      if (!response.ok) {
        return null;
      }
      const advisory = (await response.json()) as Advisory;
      this._render(advisory);
      return advisory;
    } catch {
      return null;
    }
  }

  private _render(advisory: Advisory): void {
    if (!advisory.active) {
      return;
    }
    let banner = this._container.querySelector(
      "[data-leo-advisory-banner]",
    ) as HTMLElement | null;
    if (!banner) {
      banner = this._container.ownerDocument.createElement("div");
      banner.setAttribute("data-leo-advisory-banner", "true");
      banner.setAttribute("role", "alert");
      banner.setAttribute("aria-live", "polite");
      banner.className = "leo-advisory";
      this._container.insertBefore(banner, this._container.firstChild);
    }
    const headline = advisory.headline ?? "LEO clinical safety advisory";
    const body = advisory.body ?? "";
    banner.textContent = `${headline}: ${body}`;
  }
}
