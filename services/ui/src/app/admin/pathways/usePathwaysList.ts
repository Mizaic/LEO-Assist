/**
 * Atlas trace:
 *   DO: DO-11232EFB
 *   DI: DI-CD931485
 */
"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useRouter } from "next/navigation";
import type { StatTile } from "@leo/design-system";

import { api } from "@/lib/api";
import type { PathwayTemplate } from "./templates";
import type { PlanDefinition } from "./types";

export type StatusFilter = "all" | "active" | "draft" | "retired";

export function computeStats(plans: PlanDefinition[]): StatTile[] {
  const live = plans.filter((p) => p.status === "active").length;
  const draft = plans.filter((p) => p.status === "draft").length;
  const retired = plans.filter((p) => p.status === "retired").length;
  return [
    { id: "total", label: "Pathways", value: plans.length, hint: "All defined" },
    {
      id: "live",
      label: "Live",
      value: live,
      hint: "Running on patient data",
      tone: live > 0 ? "positive" : "neutral",
    },
    {
      id: "draft",
      label: "Drafts",
      value: draft,
      hint: "Not yet published",
      tone: draft > 0 ? "warning" : "neutral",
    },
    {
      id: "retired",
      label: "Retired",
      value: retired,
      hint: "Archived for audit",
    },
  ];
}

export function filterPlans(
  plans: PlanDefinition[],
  filter: StatusFilter,
): PlanDefinition[] {
  if (filter === "all") return plans;
  return plans.filter((p) => p.status === filter);
}

export function usePathwaysList() {
  const router = useRouter();
  const [plans, setPlans] = useState<PlanDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const dialogs = usePathwayDialogs();
  const load = usePathwayLoad(setPlans, setLoading, setError);
  const mutations = usePathwayMutations({
    router,
    load,
    setPlans,
    setBusy,
    setError,
    dialogs,
  });

  const stats = useMemo(() => computeStats(plans), [plans]);
  const visible = useMemo(
    () => filterPlans(plans, statusFilter),
    [plans, statusFilter],
  );
  const counts = useMemo(
    () => ({
      all: plans.length,
      active: plans.filter((p) => p.status === "active").length,
      draft: plans.filter((p) => p.status === "draft").length,
      retired: plans.filter((p) => p.status === "retired").length,
    }),
    [plans],
  );

  return {
    plans,
    loading,
    busy,
    error,
    setError,
    statusFilter,
    setStatusFilter,
    stats,
    visible,
    counts,
    ...dialogs,
    ...mutations,
  };
}

export type PathwaysList = ReturnType<typeof usePathwaysList>;

function usePathwayDialogs() {
  const [newDialogOpen, setNewDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [publishTarget, setPublishTarget] = useState<PlanDefinition | null>(null);
  const [versionNotes, setVersionNotes] = useState("");
  const [publishing, setPublishing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PlanDefinition | null>(null);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [retireTarget, setRetireTarget] = useState<PlanDefinition | null>(null);
  return {
    newDialogOpen,
    setNewDialogOpen,
    creating,
    setCreating,
    publishTarget,
    setPublishTarget,
    versionNotes,
    setVersionNotes,
    publishing,
    setPublishing,
    deleteTarget,
    setDeleteTarget,
    deleteConfirmName,
    setDeleteConfirmName,
    deleting,
    setDeleting,
    retireTarget,
    setRetireTarget,
  };
}

function usePathwayLoad(
  setPlans: (next: PlanDefinition[]) => void,
  setLoading: (next: boolean) => void,
  setError: (next: string | null) => void,
) {
  const load = useCallback(() => {
    setLoading(true);
    api
      .get<{ entry: Array<{ resource: PlanDefinition }> }>("/fhir/PlanDefinition")
      .then((data) => setPlans((data.entry || []).map((e) => e.resource)))
      .catch((err) => {
        setError(err?.message ?? "Failed to load pathways");
      })
      .finally(() => setLoading(false));
  }, [setError, setLoading, setPlans]);

  useEffect(() => {
    load();
  }, [load]);

  return load;
}

function usePathwayMutations(args: {
  router: ReturnType<typeof useRouter>;
  load: () => void;
  setPlans: Dispatch<SetStateAction<PlanDefinition[]>>;
  setBusy: Dispatch<SetStateAction<Record<string, boolean>>>;
  setError: (next: string | null) => void;
  dialogs: ReturnType<typeof usePathwayDialogs>;
}) {
  const setBusyFor = (id: string, val: boolean) =>
    args.setBusy((prev) => ({ ...prev, [id]: val }));

  const patchStatus = async (plan: PlanDefinition, status: string) => {
    setBusyFor(plan.id, true);
    try {
      await api.put(`/fhir/PlanDefinition/${plan.id}`, { ...plan, status });
      args.setPlans((prev) =>
        prev.map((p) => (p.id === plan.id ? { ...p, status } : p)),
      );
    } catch {
      args.setError("Failed to update pathway status. Please try again.");
    } finally {
      setBusyFor(plan.id, false);
    }
  };

  return {
    patchStatus,
    handleDuplicate: (plan: PlanDefinition) =>
      duplicatePathway(plan, setBusyFor, args.load, args.setError),
    handleCreateFromTemplate: (template: PathwayTemplate) =>
      createFromTemplate(template, args.router, args.dialogs, args.setError),
    confirmPublish: () => confirmPublish(args),
    confirmDelete: () => confirmDelete(args),
    openEditor: (id: string) => args.router.push(`/admin/pathways/${id}`),
  };
}

async function duplicatePathway(
  plan: PlanDefinition,
  setBusyFor: (id: string, val: boolean) => void,
  load: () => void,
  setError: (next: string | null) => void,
) {
  setBusyFor(plan.id, true);
  try {
    const { id: _id, ...rest } = plan;
    await api.post("/fhir/PlanDefinition", {
      ...rest,
      name: `Copy of ${plan.name}`,
      status: "draft",
      version: undefined,
    });
    load();
  } catch {
    setError("Failed to duplicate pathway.");
  } finally {
    setBusyFor(plan.id, false);
  }
}

async function createFromTemplate(
  template: PathwayTemplate,
  router: ReturnType<typeof useRouter>,
  dialogs: ReturnType<typeof usePathwayDialogs>,
  setError: (next: string | null) => void,
) {
  dialogs.setCreating(true);
  try {
    const result = await api.post<{ id: string }>(
      "/fhir/PlanDefinition",
      template.payload,
    );
    router.push(`/admin/pathways/${result.id}`);
  } catch {
    setError("Could not create pathway. Please try again.");
    dialogs.setCreating(false);
  }
}

async function confirmPublish(args: {
  setPlans: Dispatch<SetStateAction<PlanDefinition[]>>;
  setError: (next: string | null) => void;
  dialogs: ReturnType<typeof usePathwayDialogs>;
}) {
  const target = args.dialogs.publishTarget;
  if (!target) return;
  args.dialogs.setPublishing(true);
  try {
    await api.put(`/fhir/PlanDefinition/${target.id}`, {
      ...target,
      status: "active",
      meta: { ...(target.meta ?? {}), versionNotes: args.dialogs.versionNotes },
    });
    args.setPlans((prev) =>
      prev.map((p) => (p.id === target.id ? { ...p, status: "active" } : p)),
    );
    args.dialogs.setPublishTarget(null);
    args.dialogs.setVersionNotes("");
  } catch {
    args.setError("Publish failed. Please try again.");
  } finally {
    args.dialogs.setPublishing(false);
  }
}

async function confirmDelete(args: {
  setPlans: Dispatch<SetStateAction<PlanDefinition[]>>;
  setError: (next: string | null) => void;
  dialogs: ReturnType<typeof usePathwayDialogs>;
}) {
  const target = args.dialogs.deleteTarget;
  if (!target) return;
  args.dialogs.setDeleting(true);
  try {
    await api.delete(`/fhir/PlanDefinition/${target.id}`);
    args.setPlans((prev) => prev.filter((p) => p.id !== target.id));
    args.dialogs.setDeleteTarget(null);
    args.dialogs.setDeleteConfirmName("");
  } catch (e) {
    args.setError(e instanceof Error ? e.message : "Failed to delete pathway.");
  } finally {
    args.dialogs.setDeleting(false);
  }
}
