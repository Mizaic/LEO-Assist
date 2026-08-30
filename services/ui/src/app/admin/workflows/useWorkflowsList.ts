"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { StatTile } from "@leo/design-system";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import PersonOutlineIcon from "@mui/icons-material/PersonOutline";
import React from "react";
import type { Workflow, CreateWorkflowPayload } from "./types";
import {
  listWorkflows,
  createWorkflow,
  deleteWorkflow,
} from "./workflowApi";

export type WorkflowDialogMode =
  | { type: "none" }
  | { type: "create" }
  | { type: "delete"; workflow: Workflow };

export function useWorkflowsList() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<WorkflowDialogMode>({ type: "none" });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listWorkflows();
      setWorkflows(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load workflows. Please retry."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleCreate = useCallback(
    async (payload: CreateWorkflowPayload) => {
      setBusy(true);
      setError(null);
      try {
        const created = await createWorkflow(payload);
        setWorkflows((prev) => [created, ...prev]);
        setDialog({ type: "none" });
        return created;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Could not create workflow. Please try again."
        );
        return null;
      } finally {
        setBusy(false);
      }
    },
    []
  );

  const handleDelete = useCallback(async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await deleteWorkflow(id);
      setWorkflows((prev) => prev.filter((w) => w.id !== id));
      setDialog({ type: "none" });
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not delete workflow. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const stats: StatTile[] = useMemo(() => {
    const total = workflows.length;
    const agentSteps = workflows.reduce((s, w) => s + (w.stepCount ?? 0), 0);
    const humanGates = workflows.reduce((s, w) => s + (w.humanCount ?? 0), 0);
    return [
      {
        id: "total",
        label: "Workflows",
        value: total,
        icon: React.createElement(AccountTreeOutlinedIcon, { fontSize: "small" }),
      },
      {
        id: "agents",
        label: "Agent Steps",
        value: agentSteps,
        icon: React.createElement(SmartToyOutlinedIcon, { fontSize: "small" }),
      },
      {
        id: "human",
        label: "Human Gates",
        value: humanGates,
        icon: React.createElement(PersonOutlineIcon, { fontSize: "small" }),
      },
    ];
  }, [workflows]);

  return {
    workflows,
    loading,
    error,
    busy,
    dialog,
    stats,
    setError,
    setDialog,
    handleCreate,
    handleDelete,
    reload: load,
  };
}
