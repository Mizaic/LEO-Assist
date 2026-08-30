"use client";

/**
 * Workflow Builder -- list page.
 *
 * Shows all workflows across services. Platform admins can create,
 * open, and delete workflows from here.
 */

import { useCallback } from "react";
import { useRouter } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import AddIcon from "@mui/icons-material/Add";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
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
import WorkflowCard from "./WorkflowCard";
import { NewWorkflowDialog, DeleteWorkflowDialog } from "./dialogs";
import { useWorkflowsList } from "./useWorkflowsList";
import type { Workflow } from "./types";

export default function WorkflowsPage() {
  const router = useRouter();
  const page = useWorkflowsList();

  const handleEdit = useCallback(
    (workflow: Workflow) => {
      router.push(`/admin/workflows/${workflow.id}`);
    },
    [router]
  );

  const toolbarActions: ToolbarAction[] = [
    {
      id: "new-workflow",
      label: "New workflow",
      icon: <AddIcon fontSize="small" />,
      variant: "primary",
      onClick: () => page.setDialog({ type: "create" }),
    },
  ];

  return (
    <Box data-testid="workflows-workspace">
      <StatHero stats={page.stats} />

      {page.error && (
        <Alert
          severity="error"
          sx={{ mb: 2 }}
          onClose={() => page.setError(null)}
        >
          {page.error}
        </Alert>
      )}

      <StickyChrome>
        <Box
          sx={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 2,
          }}
        >
          <SegmentedTabs
            tabs={[{ id: "all", label: "All workflows" }]}
            value="all"
            onChange={() => undefined}
            aria-label="Workflow filter"
          />
          <ToolbarActions actions={toolbarActions} />
        </Box>
      </StickyChrome>

      <SpringSwap swapKey="all">
        <WorkflowsBody
          page={page}
          onEdit={handleEdit}
          onDelete={(workflow) => page.setDialog({ type: "delete", workflow })}
        />
      </SpringSwap>

      {/* Dialogs */}
      <NewWorkflowDialog
        open={page.dialog.type === "create"}
        busy={page.busy}
        onClose={() => page.setDialog({ type: "none" })}
        onCreate={(payload) => {
          void page.handleCreate(payload).then((created) => {
            if (created) router.push(`/admin/workflows/${created.id}`);
          });
        }}
      />
      <DeleteWorkflowDialog
        workflow={
          page.dialog.type === "delete" ? page.dialog.workflow : null
        }
        busy={page.busy}
        onClose={() => page.setDialog({ type: "none" })}
        onConfirm={page.handleDelete}
      />
    </Box>
  );
}

function WorkflowsBody({
  page,
  onEdit,
  onDelete,
}: {
  page: ReturnType<typeof useWorkflowsList>;
  onEdit: (w: Workflow) => void;
  onDelete: (w: Workflow) => void;
}) {
  if (page.loading) return <SkeletonList rows={4} />;

  if (!page.workflows.length) {
    return (
      <EmptyState
        icon={<AccountTreeOutlinedIcon />}
        title="No workflows yet"
        body="Create a workflow to start building referral automation for a service."
        cta={{ label: "New workflow", onClick: () => page.setDialog({ type: "create" }) }}
      />
    );
  }

  return (
    <Stack spacing={1.5}>
      {page.workflows.map((w, i) => (
        <WorkflowCard
          key={w.id}
          workflow={w}
          index={i}
          onEdit={() => onEdit(w)}
          onDelete={() => onDelete(w)}
        />
      ))}
    </Stack>
  );
}
