/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-11232EFB
 *   DI: DI-CD931485
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-11232EFB")
 */
"use client";

/**
 * Pathways admin list -- Wave E Phase 6 redesign.
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: live / draft / retired / total counts.
 *   - SegmentedTabs: status filter (All / Live / Drafts / Retired).
 *   - ToolbarActions: New pathway (single primary action).
 *   - Stack of design-system PathwayCard components.
 *
 * Dialogs (NewPathwayDialog, PublishDialog, DeletePathwayDialog) and
 * template payloads live in sibling modules to keep this orchestrator
 * within the 300 LOC target.
 *
 * Design Controls: DI-LEO-AI-150, DO-LEO-AI-146, R-LEO-AI-102, VT-LEO-AI-148.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import AddIcon from "@mui/icons-material/Add";

import {
  SegmentedTabs,
  SkeletonList,
  StatHero,
  ToolbarActions,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import { api } from "@/lib/api";
import ConfirmDialog from "@/components/ConfirmDialog";
import PathwayCard from "./PathwayCard";
import {
  DeletePathwayDialog,
  NewPathwayDialog,
  PublishDialog,
} from "./dialogs";
import type { PlanDefinition } from "./types";
import type { PathwayTemplate } from "./templates";

type StatusFilter = "all" | "active" | "draft" | "retired";

function computeStats(plans: PlanDefinition[]): StatTile[] {
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

function filterPlans(
  plans: PlanDefinition[],
  filter: StatusFilter,
): PlanDefinition[] {
  if (filter === "all") return plans;
  return plans.filter((p) => p.status === filter);
}

// LONG FUNCTION: PathwaysPage owns 3 dialogs and ~10 handler closures; child
// components stay presentational. Splitting further would scatter state.
export default function PathwaysPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<PlanDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const [newDialogOpen, setNewDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);

  const [publishTarget, setPublishTarget] = useState<PlanDefinition | null>(null);
  const [versionNotes, setVersionNotes] = useState("");
  const [publishing, setPublishing] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<PlanDefinition | null>(null);
  const [deleteConfirmName, setDeleteConfirmName] = useState("");
  const [deleting, setDeleting] = useState(false);

  const [retireTarget, setRetireTarget] = useState<PlanDefinition | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      .get<{ entry: Array<{ resource: PlanDefinition }> }>(
        "/fhir/PlanDefinition",
      )
      .then((data) => setPlans((data.entry || []).map((e) => e.resource)))
      .catch((err) => {
        setError(err?.message ?? "Failed to load pathways");
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const setBusyFor = (id: string, val: boolean) =>
    setBusy((prev) => ({ ...prev, [id]: val }));

  const patchStatus = async (plan: PlanDefinition, status: string) => {
    setBusyFor(plan.id, true);
    try {
      await api.put(`/fhir/PlanDefinition/${plan.id}`, { ...plan, status });
      setPlans((prev) =>
        prev.map((p) => (p.id === plan.id ? { ...p, status } : p)),
      );
    } catch {
      setError("Failed to update pathway status. Please try again.");
    } finally {
      setBusyFor(plan.id, false);
    }
  };

  const handleDuplicate = async (plan: PlanDefinition) => {
    setBusyFor(plan.id, true);
    try {
      const { id: _id, ...rest } = plan;
      const newPlan = {
        ...rest,
        name: `Copy of ${plan.name}`,
        status: "draft",
        version: undefined,
      };
      await api.post("/fhir/PlanDefinition", newPlan);
      load();
    } catch {
      setError("Failed to duplicate pathway.");
    } finally {
      setBusyFor(plan.id, false);
    }
  };

  const handleCreateFromTemplate = async (template: PathwayTemplate) => {
    setCreating(true);
    try {
      const result = await api.post<{ id: string }>(
        "/fhir/PlanDefinition",
        template.payload,
      );
      router.push(`/admin/pathways/${result.id}`);
    } catch {
      setError("Could not create pathway. Please try again.");
      setCreating(false);
    }
  };

  const confirmPublish = async () => {
    if (!publishTarget) return;
    setPublishing(true);
    try {
      await api.put(`/fhir/PlanDefinition/${publishTarget.id}`, {
        ...publishTarget,
        status: "active",
        meta: { ...(publishTarget.meta ?? {}), versionNotes },
      });
      setPlans((prev) =>
        prev.map((p) =>
          p.id === publishTarget.id ? { ...p, status: "active" } : p,
        ),
      );
      setPublishTarget(null);
      setVersionNotes("");
    } catch {
      setError("Publish failed. Please try again.");
    } finally {
      setPublishing(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/fhir/PlanDefinition/${deleteTarget.id}`);
      setPlans((prev) => prev.filter((p) => p.id !== deleteTarget.id));
      setDeleteTarget(null);
      setDeleteConfirmName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete pathway.");
    } finally {
      setDeleting(false);
    }
  };

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

  const toolbarActions: ToolbarAction[] = [
    {
      id: "new-pathway",
      label: "New pathway",
      icon: <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => setNewDialogOpen(true),
    },
  ];

  const cardProps = (plan: PlanDefinition, index: number) => ({
    plan,
    index,
    busy: !!busy[plan.id],
    onEdit: () => router.push(`/admin/pathways/${plan.id}`),
    onPublish: () => {
      setPublishTarget(plan);
      setVersionNotes("");
    },
    onDuplicate: () => handleDuplicate(plan),
    onRetire: () => setRetireTarget(plan),
    onReactivate: () => {
      setPublishTarget(plan);
      setVersionNotes("");
    },
    onDelete: () => {
      setDeleteTarget(plan);
      setDeleteConfirmName("");
    },
  });

  return (
    <Box>
      <StatHero stats={stats} />

      {error ? (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          onClose={() => setError(null)}
        >
          {error}
        </Alert>
      ) : null}

      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 2,
          mb: 2,
        }}
      >
        <SegmentedTabs
          tabs={[
            { id: "all", label: "All", count: counts.all },
            { id: "active", label: "Live", count: counts.active },
            { id: "draft", label: "Drafts", count: counts.draft },
            { id: "retired", label: "Retired", count: counts.retired },
          ]}
          value={statusFilter}
          onChange={(id) => setStatusFilter(id as StatusFilter)}
          aria-label="Filter pathways by status"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>

      {loading ? (
        <Box aria-busy="true">
          <span aria-live="polite" style={{ position: "absolute", left: -9999, width: 1, height: 1, overflow: "hidden" }}>
            Loading pathways...
          </span>
          <SkeletonList rows={3} itemHeight={140} />
        </Box>
      ) : plans.length === 0 ? (
        <Box
          sx={{
            textAlign: "center",
            py: 8,
            border: "1px dashed",
            borderColor: "divider",
            borderRadius: 2,
            bgcolor: "#F8FAFC",
          }}
        >
          <AccountTreeIcon
            sx={{ fontSize: 48, color: "text.disabled", mb: 1 }}
          />
          <Typography color="text.secondary" gutterBottom>
            No pathways configured yet.
          </Typography>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setNewDialogOpen(true)}
            sx={{ mt: 1 }}
          >
            Create your first pathway
          </Button>
        </Box>
      ) : visible.length === 0 ? (
        <Box
          sx={{
            py: 6,
            textAlign: "center",
            color: "text.secondary",
            border: "1px dashed",
            borderColor: "divider",
            borderRadius: 2,
            bgcolor: "#F8FAFC",
          }}
        >
          <Typography variant="body2">
            No pathways match this filter.
          </Typography>
        </Box>
      ) : (
        <Stack spacing={1.5} data-testid="pathways-list">
          {visible.map((plan, i) => (
            <PathwayCard key={plan.id} {...cardProps(plan, i)} />
          ))}
        </Stack>
      )}

      <NewPathwayDialog
        open={newDialogOpen}
        onClose={() => setNewDialogOpen(false)}
        onCreate={handleCreateFromTemplate}
        creating={creating}
      />

      <PublishDialog
        target={publishTarget}
        versionNotes={versionNotes}
        publishing={publishing}
        onClose={() => setPublishTarget(null)}
        onConfirm={confirmPublish}
        onVersionNotesChange={setVersionNotes}
      />

      <DeletePathwayDialog
        target={deleteTarget}
        confirmName={deleteConfirmName}
        deleting={deleting}
        onClose={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        onConfirmNameChange={setDeleteConfirmName}
      />

      {retireTarget ? (
        <ConfirmDialog
          title="Retire this pathway?"
          body="Clinical users will stop seeing it."
          confirmLabel="Retire pathway"
          variant="danger"
          onConfirm={() => {
            patchStatus(retireTarget, "retired");
            setRetireTarget(null);
          }}
          onCancel={() => setRetireTarget(null)}
        />
      ) : null}
    </Box>
  );
}
