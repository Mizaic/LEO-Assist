"use client";

/**
 * Connector + queue + agent probe strategies (Phase 6b-vi decomposition).
 *
 * Strategies covered:
 *   - restConnector         (generic REST API call)
 *   - queuePublish          (Service Bus publish)
 *   - hitlQueue             (HITL NER + coding queue writes)
 *   - encounterLoader       (Neo4j -> encounter text bootstrap)
 *   - stagingEnrichment     (episode staging enrichment)
 *   - humanReviewGate       (auto-ready / pending-review gate)
 *   - encounterCodingAgent  (autonomous coding agent loop)
 *
 * Design Controls: DI-LEO-AI-165, DO-LEO-AI-164, VT-LEO-AI-163.
 */

import {
  C,
  InspectButton,
  MiniTable,
  Pill,
  SectionCard,
  Verdict,
  arr,
  bool,
  fmt,
  isRec,
  num,
  pl,
  safeJSON,
  str,
  trunc,
  type ProbeStrategy,
} from "./_shared";

export const restConnector: ProbeStrategy = {
  icon: "🔗",
  headline: (out) => {
    const resp = isRec(out.connector_response) ? out.connector_response : {};
    const status = num(resp.status_code ?? resp.status, 0);
    const errs = arr(out.errors);
    if (errs.length > 0) return `API call failed — ${pl(errs.length, "error")}`;
    return status > 0 ? `API call completed (${status})` : "API call completed";
  },
  Detail: ({ output, openInspector }) => {
    const resp = isRec(output.connector_response) ? output.connector_response : null;
    const errs = arr(output.errors);
    if (!resp && errs.length === 0) return <div style={{ color: C.dim, fontSize: 10 }}>No response data.</div>;
    const status = resp ? num(resp.status_code ?? resp.status, 0) : 0;
    const ok = status >= 200 && status < 300;
    return (
      <div style={{ display: "grid", gap: 8 }}>
        {resp && <Verdict passed={ok} label={ok ? `HTTP ${status} OK` : `HTTP ${status}`} detail={resp.url ? str(resp.url) : undefined} />}
        {errs.length > 0 && errs.slice(0, 3).map((e, i) => (
          <div key={i} style={{ color: C.red, fontSize: 10 }}>✗ {fmt(e)}</div>
        ))}
        {resp && <InspectButton label="View full response" onClick={() => openInspector(["connector_response"])} />}
      </div>
    );
  },
};

export const queuePublish: ProbeStrategy = {
  icon: "📤",
  headline: (out) => {
    const queued = out.queued;
    const errs = arr(out.errors);
    if (errs.length > 0) return `Queue publish failed — ${pl(errs.length, "error")}`;
    return queued ? "Message published to queue" : "Queue publish completed";
  },
  Detail: ({ output }) => {
    const queued = output.queued;
    const errs = arr(output.errors);
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <Pill label="Status" value={queued ? "published" : "pending"} color={queued ? C.green : C.dim} />
        {errs.length > 0 && <Pill label="Errors" value={errs.length} color={C.red} />}
      </div>
    );
  },
};

export const hitlQueue: ProbeStrategy = {
  icon: "🧑‍⚕️",
  headline: (out) => {
    const written = typeof out.training_labels_written === "number"
      ? out.training_labels_written
      : arr(out.training_labels_written).length;
    const errs = arr(out.errors).length;
    let h = `${pl(written, "candidate")} queued for review`;
    if (errs > 0) h += ` · ${pl(errs, "error")}`;
    return h;
  },
  Detail: ({ output }) => {
    const written = typeof output.training_labels_written === "number"
      ? output.training_labels_written
      : arr(output.training_labels_written).length;
    const errs = arr(output.errors).filter(isRec);
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ color: written > 0 ? C.green : C.dim, fontSize: 11 }}>
          {written > 0
            ? `${written} training candidate${written === 1 ? "" : "s"} written to HITL queue.`
            : "No candidates written — nothing to queue."}
        </div>
        {errs.length > 0 && (
          <MiniTable cols={["error"]} rows={errs} />
        )}
      </div>
    );
  },
};

export const encounterLoader: ProbeStrategy = {
  icon: "📥",
  headline: (out) => {
    const text = str(out.encounter_text);
    if (!text) return "No encounter text loaded";
    return `Loaded encounter text — ${text.length} chars`;
  },
  Detail: ({ output }) => {
    const text = str(output.encounter_text);
    const errs = arr(output.errors).filter(isRec);
    if (!text && errs.length === 0) {
      return <div style={{ color: C.dim, fontSize: 10 }}>No encounter text was returned.</div>;
    }
    return (
      <div style={{ display: "grid", gap: 8 }}>
        {text && (
          <SectionCard title="Encounter text (first 200 chars)" text={text} />
        )}
        {errs.length > 0 && <MiniTable cols={["error"]} rows={errs} />}
      </div>
    );
  },
};

export const stagingEnrichment: ProbeStrategy = {
  icon: "🎗️",
  headline: (out, inp) => {
    const eps = arr(inp.episode_ids).length || arr(out.episode_ids).length;
    const errs = arr(out.errors).length;
    if (eps === 0) return "No episodes to stage";
    let h = `Enriched ${pl(eps, "episode")}`;
    if (errs > 0) h += ` · ${pl(errs, "error")}`;
    return h;
  },
  Detail: ({ output, input }) => {
    const eps = arr(input.episode_ids).length || arr(output.episode_ids).length;
    const errs = arr(output.errors).filter(isRec);
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <Pill label="Episodes" value={eps} color={eps > 0 ? C.green : C.dim} />
          <Pill label="Errors" value={errs.length} color={errs.length > 0 ? C.red : C.dim} />
        </div>
        {errs.length > 0 && <MiniTable cols={["error"]} rows={errs} />}
        {eps === 0 && (
          <div style={{ color: C.dim, fontSize: 10 }}>
            Stage enrichment runs after episodes are built. No episode_ids were found in the upstream state.
          </div>
        )}
      </div>
    );
  },
};

export const humanReviewGate: ProbeStrategy = {
  icon: "🛑",
  headline: (out) => {
    const status = str(out.review_status);
    const needs = bool(out.needs_human_review);
    if (status === "auto_ready") return "Auto-ready — no human review required";
    if (needs || status === "pending_review") return "Pending human review";
    return "Review status not set";
  },
  Detail: ({ output }) => {
    const status = str(output.review_status, "(unset)");
    const needs = bool(output.needs_human_review);
    const coded = isRec(output.coded_criteria) ? output.coded_criteria : null;
    const detail = needs
      ? "A clinician must review this run before downstream steps continue."
      : status === "auto_ready"
        ? "The gate cleared the run; downstream steps can proceed automatically."
        : "The gate did not produce a decision. Check upstream coded_criteria.";
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <Verdict
          passed={status === "auto_ready"}
          label={`Status: ${status}`}
          detail={detail}
        />
        {coded && (
          <SectionCard
            title="coded_criteria"
            text={trunc(safeJSON(coded), 200)}
          />
        )}
      </div>
    );
  },
};

export const encounterCodingAgent: ProbeStrategy = {
  icon: "🤖",
  headline: (out) => {
    const verdict = isRec(out.verdict) ? out.verdict : null;
    const messages = arr(out.messages).length;
    const errs = arr(out.errors).length;
    if (errs > 0) return `Agent errored after ${pl(messages, "turn")}`;
    if (!verdict) return `Agent ran ${pl(messages, "turn")} — no verdict yet`;
    const decision = str(verdict.decision) || str(verdict.status) || "verdict";
    return `Verdict: ${decision} (${pl(messages, "turn")})`;
  },
  Detail: ({ output }) => {
    const verdict = isRec(output.verdict) ? output.verdict : null;
    const messages = arr(output.messages).length;
    const iters = num(output.tool_iterations);
    const inTok = num(output.input_tokens);
    const outTok = num(output.output_tokens);
    const errs = arr(output.errors).filter(isRec);
    return (
      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          <Pill label="Turns" value={messages} color={C.blue} />
          <Pill label="Tool iterations" value={iters} color={iters > 0 ? C.purple : C.dim} />
          <Pill label="In tokens" value={inTok} />
          <Pill label="Out tokens" value={outTok} />
        </div>
        {verdict ? (
          <Verdict
            passed={str(verdict.decision) === "approve" || str(verdict.status) === "ok"}
            label={`Decision: ${str(verdict.decision) || str(verdict.status) || "n/a"}`}
            detail={str(verdict.reason) || str(verdict.summary) || undefined}
          />
        ) : (
          <div style={{ color: C.dim, fontSize: 10 }}>
            The agent did not emit a verdict. Inspect messages to see the tool-call trace.
          </div>
        )}
        {errs.length > 0 && <MiniTable cols={["error"]} rows={errs} />}
      </div>
    );
  },
};
