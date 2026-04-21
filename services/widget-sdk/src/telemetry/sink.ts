/**
 * TelemetrySink - mandatory disclosure-engagement telemetry.
 *
 * Atlas trace:
 *   DO: DO-23DDE984
 *   DI: DI-5F121122
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-23DDE984")
 *
 * Required (not opt-in) telemetry. The host has no public API to
 * disable, mute, or rewrite the analytics endpoint after the sink
 * is constructed. The endpoint URL is captured into a private,
 * non-writable property at construction time.
 *
 * Failure mode: when fetch fails the event is kept in a bounded
 * in-memory queue and retried with exponential backoff. The host
 * is notified via an onDegraded(true) callback so it can show a
 * passive indicator. SBAR rendering is never blocked - record() is
 * fire-and-forget and never throws into the caller.
 */

import type { TelemetryEnvelope, TelemetryEventType } from "./types";

const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 30_000] as const;
const MAX_QUEUE = 200;

let _instanceCounter = 0;
function _newInstanceId(): string {
  _instanceCounter += 1;
  const ts = Date.now().toString(36);
  return `wi-${ts}-${_instanceCounter}`;
}

export interface TelemetrySinkOptions {
  analyticsUrl: string;
  assessmentId: string;
  onDegraded?: (isDegraded: boolean) => void;
  fetcher?: typeof fetch;
}

export class TelemetrySink {
  private readonly _queue: TelemetryEnvelope[] = [];
  private _eventCounter = 0;
  private _retryAttempt = 0;
  private _scheduled: ReturnType<typeof setTimeout> | null = null;
  private _isDegraded = false;
  private _flushing = false;

  constructor(options: TelemetrySinkOptions) {
    if (!options.analyticsUrl) {
      throw new Error("leo-widget: telemetry analyticsUrl is required");
    }
    if (!options.assessmentId) {
      throw new Error("leo-widget: telemetry assessmentId is required");
    }
    Object.defineProperty(this, "analyticsUrl", {
      value: options.analyticsUrl,
      writable: false,
      configurable: false,
      enumerable: true,
    });
    Object.defineProperty(this, "assessmentId", {
      value: options.assessmentId,
      writable: false,
      configurable: false,
      enumerable: true,
    });
    Object.defineProperty(this, "instanceId", {
      value: _newInstanceId(),
      writable: false,
      configurable: false,
      enumerable: true,
    });
    Object.defineProperty(this, "_onDegraded", {
      value: options.onDegraded ?? null,
      writable: false,
      configurable: false,
      enumerable: false,
    });
    Object.defineProperty(this, "_fetcher", {
      value: options.fetcher ?? globalThis.fetch?.bind(globalThis),
      writable: false,
      configurable: false,
      enumerable: false,
    });
  }

  // Read-only public properties (declared via defineProperty above).
  readonly analyticsUrl!: string;
  readonly assessmentId!: string;
  readonly instanceId!: string;

  private get _onDegradedCb(): ((d: boolean) => void) | null {
    return (this as unknown as { _onDegraded: ((d: boolean) => void) | null })
      ._onDegraded;
  }

  private get _fetchImpl(): typeof fetch {
    return (this as unknown as { _fetcher: typeof fetch })._fetcher;
  }

  record(
    type: TelemetryEventType,
    payload: Record<string, unknown> = {},
  ): TelemetryEnvelope {
    this._eventCounter += 1;
    const envelope: TelemetryEnvelope = {
      widget_instance_id: this.instanceId,
      event_id: this._eventCounter,
      type,
      assessment_id: this.assessmentId,
      emitted_at_ms: Date.now(),
      payload: Object.freeze({ ...payload }),
    };
    if (this._queue.length >= MAX_QUEUE) {
      this._queue.shift();
    }
    this._queue.push(envelope);
    void this._flush();
    return envelope;
  }

  private async _flush(): Promise<void> {
    if (this._flushing) {
      return;
    }
    if (this._queue.length === 0) {
      return;
    }
    this._flushing = true;
    try {
      while (this._queue.length > 0) {
        const next = this._queue[0];
        const ok = await this._send(next);
        if (!ok) {
          this._scheduleRetry();
          return;
        }
        this._queue.shift();
        this._retryAttempt = 0;
        this._setDegraded(false);
      }
    } finally {
      this._flushing = false;
    }
  }

  private async _send(envelope: TelemetryEnvelope): Promise<boolean> {
    try {
      const response = await this._fetchImpl(this.analyticsUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(envelope),
        credentials: "omit",
        mode: "cors",
        keepalive: true,
      });
      if (!response.ok) {
        return false;
      }
      return true;
    } catch {
      return false;
    }
  }

  private _scheduleRetry(): void {
    this._setDegraded(true);
    const delay = BACKOFF_MS[Math.min(this._retryAttempt, BACKOFF_MS.length - 1)];
    this._retryAttempt += 1;
    if (this._scheduled !== null) {
      clearTimeout(this._scheduled);
    }
    this._scheduled = setTimeout(() => {
      this._scheduled = null;
      void this._flush();
    }, delay);
  }

  private _setDegraded(value: boolean): void {
    if (this._isDegraded === value) {
      return;
    }
    this._isDegraded = value;
    const cb = this._onDegradedCb;
    if (cb) {
      try {
        cb(value);
      } catch {
        // swallow - never throw into the SBAR render path.
      }
    }
  }

  /** test-only inspection; queue length, current degraded flag */
  _stateForTesting(): { queueLength: number; isDegraded: boolean } {
    return {
      queueLength: this._queue.length,
      isDegraded: this._isDegraded,
    };
  }
}
