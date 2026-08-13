/**
 * Atlas trace:
 *   DI: DI-47D2CD86, DI-6BD7B681
 */
"use client";

import { useEffect, useState } from "react";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import { EmptyState, FilterBar } from "@leo/design-system";

import {
  approveSurfaceFormMapping,
  deactivateSurfaceFormMapping,
  fetchGroupedSurfaceForms,
  type ConceptGroup,
} from "@/lib/api/legacy";

export function LiveDictionaryPane({
  search,
  onSearchChange,
}: {
  search: string;
  onSearchChange: (value: string) => void;
}) {
  const [groups, setGroups] = useState<ConceptGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchGroupedSurfaceForms(search || undefined, 50, 0)
      .then((page) => {
        if (!cancelled) setGroups(page.items || []);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search]);

  return (
    <div data-testid="live-dictionary" style={{ minHeight: 0, overflow: "auto", paddingBottom: 32 }}>
      <FilterBar
        search={search}
        onSearchChange={onSearchChange}
        searchPlaceholder="Search a live phrase or code"
        aria-label="Search live dictionary"
      />
      {error ? <p style={{ color: "#B91C1C" }}>{error}</p> : null}
      {!loading && groups.length === 0 ? (
        <EmptyState
          icon={<TextFieldsOutlinedIcon />}
          title="No live phrases on this page"
          body="Search a phrase or a code to see what the pipeline already uses."
        />
      ) : (
        groups.map((group) => (
          <LiveGroup
            key={group.concept_id}
            group={group}
            onChange={() =>
              fetchGroupedSurfaceForms(search || undefined, 50, 0).then((page) =>
                setGroups(page.items || []),
              )
            }
          />
        ))
      )}
    </div>
  );
}

function LiveGroup({
  group,
  onChange,
}: {
  group: ConceptGroup;
  onChange: () => void;
}) {
  return (
    <article
      style={{
        background: "#fff",
        borderRadius: 12,
        padding: 16,
        marginTop: 12,
      }}
    >
      <h3 style={{ margin: 0, fontSize: 16 }}>{group.concept_fsn}</h3>
      <p style={{ margin: "4px 0 8px", fontSize: 13, color: "#596577" }}>
        {group.concept_id}
        {group.semantic_tag ? ` · ${group.semantic_tag}` : ""}
        {group.icd10_term ? ` · ICD-10: ${group.icd10}` : ""}
        {group.opcs4 ? ` · OPCS-4: ${group.opcs4}` : ""}
        {group.opcs4_term ? ` ${group.opcs4_term}` : ""}
      </p>
      <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {group.surface_forms.map((alias) => (
          <li
            key={`${alias.normalized}-${alias.status || "live"}`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 0",
            }}
          >
            <span>
              {alias.form}
              {alias.status && alias.status !== "approved" ? ` (${alias.status})` : ""}
            </span>
            {alias.status === "pending" ? (
              <button
                type="button"
                aria-label={`Approve alias ${alias.form}`}
                onClick={() =>
                  approveSurfaceFormMapping(alias.normalized, {
                    conceptId: group.concept_id,
                  }).then(onChange)
                }
              >
                Approve
              </button>
            ) : null}
            {alias.status !== "deactivated" ? (
              <button
                type="button"
                aria-label={`Deactivate alias ${alias.form}`}
                onClick={() =>
                  deactivateSurfaceFormMapping(alias.normalized).then(onChange)
                }
              >
                Deactivate
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </article>
  );
}
