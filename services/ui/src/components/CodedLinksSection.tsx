"use client";

import { useEffect, useState } from "react";
import {
  deleteCodedLink,
  fetchEncounterCodedLinks,
  recodeCodedLink,
} from "@/lib/api";
import type { CodedLink, Correction, TermSearchResult } from "@/lib/types";
import TermSearch from "./TermSearch";

interface Props {
  patientId: string;
  encounterId: string;
  onCorrection: (c: Correction) => void;
  refreshTrigger?: number;
  onLinksChange?: (links: CodedLink[]) => void;
}

export default function CodedLinksSection({
  patientId,
  encounterId,
  onCorrection,
  refreshTrigger,
  onLinksChange,
}: Props) {
  const [links, setLinks] = useState<CodedLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recodeTarget, setRecodeTarget] = useState<CodedLink | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const refresh = refreshTrigger ?? 0;

  useEffect(() => {
    setLoading(true);
    fetchEncounterCodedLinks(patientId, encounterId)
      .then((data) => {
        setLinks(data);
        onLinksChange?.(data);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Could not load coded links."),
      )
      .finally(() => setLoading(false));
  }, [patientId, encounterId, refresh, onLinksChange]);

  async function handleRemove(link: CodedLink) {
    if (!link.concept_id) return;
    setRemoving(link.concept_id);
    try {
      await deleteCodedLink(patientId, encounterId, link.concept_id);
      const next = links.filter((l) => l.concept_id !== link.concept_id);
      setLinks(next);
      onLinksChange?.(next);
      onCorrection({
        type: "remove",
        text: link.term ?? link.concept_id,
        detail: `Removed coded link ${link.concept_id}`,
        time: new Date().toISOString(),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed.");
    } finally {
      setRemoving(null);
    }
  }

  function handleRecodeSelect(result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }) {
    if (!recodeTarget) return;
    const mods = modifiers && (modifiers.value || modifiers.unit || modifiers.reference_range || modifiers.interpretation)
      ? { value: modifiers.value, unit: modifiers.unit, reference_range: modifiers.reference_range, interpretation: modifiers.interpretation }
      : undefined;
    recodeCodedLink(patientId, encounterId, recodeTarget.concept_id, {
      new_concept_id: result.snomed_concept_id,
      term: result.term,
      read_code: result.read_code,
      semantic_tag: recodeTarget.semantic_tag ?? undefined,
      modifiers: mods,
    })
      .then(() => {
        const next = links.map((l) =>
          l.concept_id === recodeTarget.concept_id
            ? {
                ...l,
                concept_id: result.snomed_concept_id,
                term: result.term,
                read_code: result.read_code,
              }
            : l
        );
        setLinks(next);
        onLinksChange?.(next);
        onCorrection({
          type: "recode",
          text: `${recodeTarget.term ?? recodeTarget.concept_id} → ${result.term}`,
          detail: `Recoded to ${result.snomed_concept_id}`,
          time: new Date().toISOString(),
        });
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Recode failed."),
      )
      .finally(() => setRecodeTarget(null));
  }

  if (loading) return <div style={{ padding: 12, fontSize: 13, color: "#64748b" }}>Loading coded links…</div>;
  if (error) return <div style={{ padding: 12, fontSize: 13, color: "#b91c1c" }}>{error}</div>;

  return (
    <>
      <div style={{ borderTop: "1px solid #e2e8f0", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: "#334155", padding: "12px 16px", borderBottom: "1px solid #e2e8f0", flexShrink: 0 }}>
          Coded terms ({links.length})
        </h3>
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "8px 0" }}>
          {links.length === 0 ? (
            <div style={{ padding: 16, fontSize: 13, color: "#94a3b8" }}>
              No coded terms yet. Select text and click &quot;Code selection&quot; to add.
            </div>
          ) : links.map((link) => (
            <div
              key={link.concept_id}
              style={{
                padding: "12px 16px",
                margin: "0 12px 8px",
                border: "none",
                borderBottom: "1px solid #f1f5f9",
                borderRadius: 0,
                fontSize: 13,
                background: "#fff",
              }}
            >
              <div style={{ fontWeight: 500, color: "#334155", marginBottom: 4, lineHeight: 1.4 }}>
                {link.term ?? link.concept_id}
              </div>
              {Boolean(
                link.modifiers?.value != null ||
                  link.modifiers?.unit ||
                  link.modifiers?.reference_range ||
                  link.modifiers?.interpretation,
              ) && (
                <div style={{ color: "#059669", fontSize: 12, marginBottom: 4 }}>
                  {[link.modifiers?.value, link.modifiers?.unit]
                    .filter((x): x is string | number => x != null && x !== "")
                    .map(String)
                    .join(" ")}
                  {link.modifiers?.reference_range ? (
                    <span style={{ color: "#64748b", marginLeft: 6 }}>
                      [{String(link.modifiers.reference_range)}]
                    </span>
                  ) : null}
                  {link.modifiers?.interpretation ? (
                    <span style={{ color: "#6366f1", marginLeft: 6, fontWeight: 500 }}>
                      {String(link.modifiers.interpretation)}
                    </span>
                  ) : null}
                </div>
              )}
              <div style={{ color: "#64748b", fontFamily: "var(--font-mono)", fontSize: 11, marginBottom: 8 }}>
                {link.concept_id}
                {link.read_code && ` · ${link.read_code}`}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={() => setRecodeTarget(link)}
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                    border: "1px solid #e2e8f0",
                    borderRadius: 6,
                    background: "#fff",
                    cursor: "pointer",
                  }}
                >
                  Recode
                </button>
                <button
                  onClick={() => handleRemove(link)}
                  disabled={removing === link.concept_id}
                  style={{
                    padding: "6px 12px",
                    fontSize: 12,
                    border: "1px solid #fecaca",
                    borderRadius: 6,
                    background: "#fff",
                    color: "#dc2626",
                    cursor: removing === link.concept_id ? "not-allowed" : "pointer",
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {recodeTarget && (
        <TermSearch
          onSelect={handleRecodeSelect}
          onClose={() => setRecodeTarget(null)}
          onCorrection={onCorrection}
          captureValueUnit
          confirmLabel="Recode"
          initialModifiers={
            recodeTarget.modifiers?.value != null || recodeTarget.modifiers?.unit || recodeTarget.modifiers?.reference_range || recodeTarget.modifiers?.interpretation
              ? {
                  value: recodeTarget.modifiers.value as string | number | undefined,
                  unit: recodeTarget.modifiers.unit as string | undefined,
                  reference_range: recodeTarget.modifiers.reference_range as string | undefined,
                  interpretation: recodeTarget.modifiers.interpretation as string | undefined,
                }
              : undefined
          }
        />
      )}
    </>
  );
}
