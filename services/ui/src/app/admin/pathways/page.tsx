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
 *
 * PathwayCard is defined in ./PathwayCard.tsx and imported below.
 * It uses framer-motion for entrance animations:
 *   import { motion as fm } from "framer-motion";
 *   function PathwayCard({ plan, index }: CardProps) { ... }
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import AddIcon from "@mui/icons-material/Add";
import {
  EmptyState,
  SegmentedTabs,
  SkeletonList,
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type ToolbarAction,
} from "@leo/design-system";

import ConfirmDialog from "@/components/ConfirmDialog";
import PathwayCard from "./PathwayCard";
import {
  DeletePathwayDialog,
  NewPathwayDialog,
  PublishDialog,
} from "./dialogs";
import type { PlanDefinition } from "./types";
import {
  usePathwaysList,
  type PathwaysList,
  type StatusFilter,
} from "./usePathwaysList";

export default function PathwaysPage() {
  const page = usePathwaysList();
  return (
    <Box data-testid="pathways-workspace">
      <StatHero stats={page.stats} />
      {page.error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => page.setError(null)}>
          {page.error}
        </Alert>
      ) : null}
      <PathwaysChrome page={page} />
      <SpringSwap swapKey={page.statusFilter}>
        <PathwaysBody page={page} />
      </SpringSwap>
      <PathwaysDialogs page={page} />
    </Box>
  );
}

function PathwaysChrome({ page }: { page: PathwaysList }) {
  const toolbarActions: ToolbarAction[] = [
    {
      id: "new-pathway",
      label: "New pathway",
      icon: <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => page.setNewDialogOpen(true),
    },
  ];
  return (
    <StickyChrome testId="pathways-chrome">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <SegmentedTabs
          tabs={[
            { id: "all", label: "All", count: page.counts.all },
            { id: "active", label: "Live", count: page.counts.active },
            { id: "draft", label: "Drafts", count: page.counts.draft },
            { id: "retired", label: "Retired", count: page.counts.retired },
          ]}
          value={page.statusFilter}
          onChange={(id) => page.setStatusFilter(id as StatusFilter)}
          aria-label="Filter pathways by status"
        />
        <ToolbarActions actions={toolbarActions} />
      </div>
    </StickyChrome>
  );
}

function PathwaysBody({ page }: { page: PathwaysList }) {
  if (page.loading) {
    return (
      <Box aria-busy="true">
        <span aria-live="polite" style={{ position: "absolute", left: -9999, width: 1, height: 1, overflow: "hidden" }}>
          Loading pathways...
        </span>
        <SkeletonList rows={3} itemHeight={140} />
      </Box>
    );
  }
  if (page.plans.length === 0) {
    return (
      <EmptyState
        icon={<AccountTreeIcon />}
        title="No pathways configured yet."
        body="Create one to start a care workflow."
        cta={{
          label: "Create your first pathway",
          onClick: () => page.setNewDialogOpen(true),
          icon: <AddIcon fontSize="small" />,
        }}
      />
    );
  }
  if (page.visible.length === 0) {
    return (
      <EmptyState
        icon={<AccountTreeIcon />}
        title="No pathways match this filter."
        body="Try All, Live, Drafts, or Retired."
      />
    );
  }
  return (
    <Box data-testid="pathways-list" sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
      {page.visible.map((plan, i) => (
        <PathwayCard key={plan.id} {...cardProps(page, plan, i)} />
      ))}
    </Box>
  );
}

function cardProps(page: PathwaysList, plan: PlanDefinition, index: number) {
  return {
    plan,
    index,
    busy: !!page.busy[plan.id],
    onEdit: () => page.openEditor(plan.id),
    onPublish: () => {
      page.setPublishTarget(plan);
      page.setVersionNotes("");
    },
    onDuplicate: () => page.handleDuplicate(plan),
    onRetire: () => page.setRetireTarget(plan),
    onReactivate: () => {
      page.setPublishTarget(plan);
      page.setVersionNotes("");
    },
    onDelete: () => {
      page.setDeleteTarget(plan);
      page.setDeleteConfirmName("");
    },
  };
}

function PathwaysDialogs({ page }: { page: PathwaysList }) {
  return (
    <>
      <NewPathwayDialog
        open={page.newDialogOpen}
        onClose={() => page.setNewDialogOpen(false)}
        onCreate={page.handleCreateFromTemplate}
        creating={page.creating}
      />
      <PublishDialog
        target={page.publishTarget}
        versionNotes={page.versionNotes}
        publishing={page.publishing}
        onClose={() => page.setPublishTarget(null)}
        onConfirm={page.confirmPublish}
        onVersionNotesChange={page.setVersionNotes}
      />
      <DeletePathwayDialog
        target={page.deleteTarget}
        confirmName={page.deleteConfirmName}
        deleting={page.deleting}
        onClose={() => page.setDeleteTarget(null)}
        onConfirm={page.confirmDelete}
        onConfirmNameChange={page.setDeleteConfirmName}
      />
      {page.retireTarget ? (
        <ConfirmDialog
          title="Retire this pathway?"
          body="Clinical users will stop seeing it."
          confirmLabel="Retire pathway"
          variant="danger"
          onConfirm={() => {
            void page.patchStatus(page.retireTarget as PlanDefinition, "retired");
            page.setRetireTarget(null);
          }}
          onCancel={() => page.setRetireTarget(null)}
        />
      ) : null}
    </>
  );
}
