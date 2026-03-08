"use client";

import { useEffect, useState } from "react";
import type { FieldMappingRow } from "../config/types";

interface SchemaFields {
  topKey: string;
  fields: Array<{ name: string; type: string; description: string; required: boolean }>;
}

export function buildDefaultRows(
  topKey: string,
  fields: Array<{ name: string; type: string; description: string; required: boolean }>,
): FieldMappingRow[] {
  return fields.map((f) => ({
    id: `${topKey}.${f.name}`,
    llmField: `${topKey}[].${f.name}`,
    type: f.type,
    description: f.description,
    required: f.required,
    statePath: "",
    custom: false,
  }));
}

export function useFieldMappings(promptConfigId: string, initialised: boolean, onInitRows: (rows: FieldMappingRow[]) => void) {
  const [schemaFields, setSchemaFields] = useState<SchemaFields | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!promptConfigId) return;
    setLoading(true);
    setError(null);
    fetch(`/api/prompts/${promptConfigId}`, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((data) => {
        const raw = data.outputSchema;
        if (!raw) {
          setSchemaFields(null);
          return;
        }
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        const topProps: Record<string, unknown> = parsed?.properties ?? {};
        for (const [topKey, propDef] of Object.entries(topProps)) {
          const prop = propDef as Record<string, unknown>;
          if (prop?.type !== "array") continue;
          const itemProps = (prop.items as Record<string, unknown>)?.properties as Record<string, unknown> | undefined;
          const required = ((prop.items as Record<string, unknown>)?.required as string[]) ?? [];
          if (!itemProps) continue;
          const fields = Object.entries(itemProps).map(([name, def]) => {
            const d = def as Record<string, unknown>;
            const t = Array.isArray(d.type) ? (d.type as string[]).join(" | ") : String(d.type ?? "");
            return { name, type: t, description: String(d.description ?? ""), required: required.includes(name) };
          });
          setSchemaFields({ topKey, fields });
          if (!initialised) onInitRows(buildDefaultRows(topKey, fields));
          return;
        }
        setSchemaFields(null);
      })
      .catch((e) => {
        setSchemaFields(null);
        setError(e instanceof Error ? e.message : "Failed to load schema");
      })
      .finally(() => setLoading(false));
  }, [promptConfigId, initialised, onInitRows]);

  return { schemaFields, loading, error };
}

