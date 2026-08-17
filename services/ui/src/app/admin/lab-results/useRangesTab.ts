/**
 * Atlas trace:
 *   DI: DI-3F771AFB
 */
"use client";

import { useEffect, useState } from "react";

import { listOrgs } from "@/lib/api/admin";

import { deleteReferenceRange, saveReferenceRange } from "./api";
import { EMPTY_RANGE, type RangeDraft, type RangeOrgOption } from "./rangeDraft";

function numOrNull(v: string): number | null {
  const n = Number(v);
  return v.trim() && Number.isFinite(n) ? n : null;
}

export function useRangesTab(args: {
  conceptId: string;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  const [draft, setDraft] = useState<RangeDraft>(EMPTY_RANGE);
  const [orgs, setOrgs] = useState<RangeOrgOption[]>([]);
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listOrgs()
      .then((rows) =>
        setOrgs(
          rows.map((row) => ({
            id: row.id,
            name: row.name,
            type: row.type,
            odsCode: row.odsCode,
          })),
        ),
      )
      .catch(() => setOrgs([]));
  }, []);

  return {
    draft,
    orgs,
    pending,
    saving,
    deleteId,
    error,
    patchDraft: (patch: Partial<RangeDraft>) => setDraft((prev) => ({ ...prev, ...patch })),
    setPending,
    setDeleteId,
    setError,
    handleAdd: () =>
      addRange({ conceptId: args.conceptId, draft, setDraft, setPending, setSaving, setError, onRefresh: args.onRefresh, onToast: args.onToast }),
    handleDelete: (id: string) =>
      removeRange({ conceptId: args.conceptId, id, setDeleteId, setError, onRefresh: args.onRefresh, onToast: args.onToast }),
  };
}

async function addRange(ctx: {
  conceptId: string;
  draft: RangeDraft;
  setDraft: (next: RangeDraft) => void;
  setPending: (next: boolean) => void;
  setSaving: (next: boolean) => void;
  setError: (next: string | null) => void;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  ctx.setSaving(true);
  ctx.setError(null);
  try {
    await saveReferenceRange(ctx.conceptId, {
      org_id: ctx.draft.orgId,
      sex: ctx.draft.sex,
      age_min: numOrNull(ctx.draft.ageMin),
      age_max: numOrNull(ctx.draft.ageMax),
      low: numOrNull(ctx.draft.low),
      high: numOrNull(ctx.draft.high),
      critical_low: numOrNull(ctx.draft.critLow),
      critical_high: numOrNull(ctx.draft.critHigh),
      source: ctx.draft.source,
    });
    ctx.setDraft(EMPTY_RANGE);
    ctx.setPending(false);
    ctx.onToast("Range added.");
    await ctx.onRefresh();
  } catch (exc) {
    ctx.setError(exc instanceof Error ? exc.message : "Unable to save range.");
  } finally {
    ctx.setSaving(false);
  }
}

async function removeRange(ctx: {
  conceptId: string;
  id: string;
  setDeleteId: (next: string | null) => void;
  setError: (next: string | null) => void;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  ctx.setDeleteId(null);
  ctx.setError(null);
  try {
    await deleteReferenceRange(ctx.conceptId, ctx.id);
    ctx.onToast("Range removed.");
    await ctx.onRefresh();
  } catch (exc) {
    ctx.setError(exc instanceof Error ? exc.message : "Unable to remove range.");
  }
}
