/**
 * Atlas trace:
 *   DI: DI-3F771AFB
 */
"use client";

import { useState } from "react";

import { deleteUnitConversion, saveUnitConversion } from "./api";

export function useConversionsTab(args: {
  conceptId: string;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  const [unit, setUnit] = useState("");
  const [factor, setFactor] = useState("1");
  const [offset, setOffset] = useState("0");
  const [pending, setPending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [deleteUnit, setDeleteUnit] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return {
    unit,
    factor,
    offset,
    pending,
    saving,
    deleteUnit,
    error,
    setUnit,
    setFactor,
    setOffset,
    setPending,
    setDeleteUnit,
    setError,
    handleAdd: () =>
      addConversion({
        conceptId: args.conceptId,
        unit,
        factor,
        offset,
        setUnit,
        setFactor,
        setOffset,
        setPending,
        setSaving,
        setError,
        onRefresh: args.onRefresh,
        onToast: args.onToast,
      }),
    handleDelete: (value: string) =>
      removeConversion({
        conceptId: args.conceptId,
        unit: value,
        setDeleteUnit,
        setError,
        onRefresh: args.onRefresh,
        onToast: args.onToast,
      }),
  };
}

async function addConversion(ctx: {
  conceptId: string;
  unit: string;
  factor: string;
  offset: string;
  setUnit: (next: string) => void;
  setFactor: (next: string) => void;
  setOffset: (next: string) => void;
  setPending: (next: boolean) => void;
  setSaving: (next: boolean) => void;
  setError: (next: string | null) => void;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  if (!ctx.unit.trim()) {
    ctx.setPending(false);
    ctx.setError("Enter a unit abbreviation.");
    return;
  }
  ctx.setSaving(true);
  ctx.setError(null);
  try {
    await saveUnitConversion(ctx.conceptId, {
      unit: ctx.unit.trim(),
      factor: Number(ctx.factor),
      offset: Number(ctx.offset),
    });
    ctx.setUnit("");
    ctx.setFactor("1");
    ctx.setOffset("0");
    ctx.setPending(false);
    ctx.onToast("Conversion added.");
    await ctx.onRefresh();
  } catch (exc) {
    ctx.setError(exc instanceof Error ? exc.message : "Unable to save conversion.");
  } finally {
    ctx.setSaving(false);
  }
}

async function removeConversion(ctx: {
  conceptId: string;
  unit: string;
  setDeleteUnit: (next: string | null) => void;
  setError: (next: string | null) => void;
  onRefresh: () => Promise<void>;
  onToast: (msg: string) => void;
}) {
  ctx.setDeleteUnit(null);
  ctx.setError(null);
  try {
    await deleteUnitConversion(ctx.conceptId, ctx.unit);
    ctx.onToast("Conversion removed.");
    await ctx.onRefresh();
  } catch (exc) {
    ctx.setError(exc instanceof Error ? exc.message : "Unable to remove conversion.");
  }
}
