/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   Also implements: DO-DA9FD5E8
 *   DI: DI-340279C1, DI-6424B6FC
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CFA1ED55")
 */
"use client";

/**
 * Domains -- Wave E Phase 3c redesign
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145.
 *
 * DomainCard is defined in ./_components/DomainCard.tsx and imported
 * below. It uses framer-motion for entrance animations:
 *   import { motion as fm } from "framer-motion";
 *   function DomainCard({ domain, onEdit, onDelete }: DomainCardProps) { ... }
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Snackbar from "@mui/material/Snackbar";
import AddIcon from "@mui/icons-material/Add";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import {
  EmptyState,
  FilterBar,
  SegmentedTabs,
  SkeletonList,
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type ToolbarAction,
} from "@leo/design-system";

import ConfirmDialog from "@/components/ConfirmDialog";
import DomainCard from "./_components/DomainCard";
import { DomainFormDialogs } from "./_components/DomainFormDialogs";
import { DOMAINS_PAGE_SX } from "./_components/domainConstants";
import { useDomainsList, type DomainsList } from "./_components/useDomainsList";

export default function DomainsListPage() {
  const page = useDomainsList();
  return (
    <Box data-testid="domains-workspace" sx={DOMAINS_PAGE_SX}>
      <StatHero stats={page.stats} />
      {page.error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => page.setError(null)}>
          {page.error}
        </Alert>
      ) : null}
      <DomainsToolbar page={page} />
      <DomainsNotices page={page} />
      <SpringSwap swapKey={page.sourceFilter + ":" + page.searchText}>
        <DomainsBody page={page} />
      </SpringSwap>
      <DomainsDialogs page={page} />
    </Box>
  );
}

function DomainsNotices({ page }: { page: DomainsList }) {
  return (
    <>
      {!page.isPlatformAdmin ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          You can view areas and export code lists. Only a platform admin can create areas or change codes.
        </Alert>
      ) : null}
      {page.sourceFilter === "nice" ? <NiceNotice isPlatformAdmin={page.isPlatformAdmin} /> : null}
    </>
  );
}

function DomainsDialogs({ page }: { page: DomainsList }) {
  return (
    <>
      <DomainFormDialogs
        createOpen={page.createOpen}
        editTarget={page.editTarget}
        onCloseCreate={() => page.setCreateOpen(false)}
        onCloseEdit={() => page.setEditTarget(null)}
        onCreate={page.handleCreate}
        onEdit={page.handleEdit}
      />
      {page.deleteTarget ? (
        <ConfirmDialog
          title="Delete area?"
          body={`Permanently delete "${page.deleteTarget.name}" and all its subdomains. This cannot be undone.`}
          confirmLabel="Delete"
          variant="danger"
          onConfirm={() => void page.handleDelete(page.deleteTarget!)}
          onCancel={() => page.setDeleteTarget(null)}
        />
      ) : null}
      <Snackbar
        open={Boolean(page.snackMsg)}
        autoHideDuration={3000}
        onClose={() => page.setSnackMsg(null)}
        message={page.snackMsg}
      />
    </>
  );
}

function DomainsToolbar({ page }: { page: DomainsList }) {
  const showCreateButton = page.showCreateButton;
  const toolbarActions: ToolbarAction[] = showCreateButton
    ? [{
        id: "create-area",
        label: "Create area",
        icon: <AddIcon fontSize="small" />,
        variant: "primary",
        onClick: () => page.setCreateOpen(true),
      }]
    : [];
  return (
    <StickyChrome testId="domains-chrome">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <SegmentedTabs
          tabs={[
            { id: "all", label: "All", count: page.counts.total },
            { id: "nice", label: "NICE", count: page.counts.nice },
            { id: "platform", label: "Built-in", count: page.counts.platform },
            { id: "tenant", label: "Your organisation", count: page.counts.tenant },
          ]}
          value={page.sourceFilter}
          onChange={(id) => page.setSourceFilter(id as typeof page.sourceFilter)}
          aria-label="Filter areas by source"
        />
        {toolbarActions.length > 0 ? <ToolbarActions actions={toolbarActions} /> : null}
      </div>
      <div style={{ marginTop: 12 }}>
        <FilterBar
          search={page.searchText}
          onSearchChange={page.setSearchText}
          searchPlaceholder="Search areas by name or description"
          aria-label="Search clinical areas"
        />
      </div>
    </StickyChrome>
  );
}

function NiceNotice({ isPlatformAdmin }: { isPlatformAdmin: boolean }) {
  return (
    <Alert severity="info" sx={{ mb: 2 }}>
      {isPlatformAdmin
        ? "These areas came from official NICE guidelines. You can add more codes to them, but you cannot delete them."
        : "These areas came from official NICE guidelines. You can view them and export code lists. Only a platform admin can add or change codes."}
    </Alert>
  );
}

function DomainsBody({ page }: { page: DomainsList }) {
  if (page.loading) {
    return <SkeletonList rows={3} itemHeight={168} gap={16} data-testid="domains-skeleton" />;
  }
  if (page.domains.length === 0) {
    return (
      <EmptyState
        icon={<FolderOpenOutlinedIcon />}
        title={emptyTitle(page.sourceFilter, page.isPlatformAdmin)}
        body={emptyBody(page.sourceFilter, page.isPlatformAdmin)}
      />
    );
  }
  if (page.filtered.length === 0) {
    return <Alert severity="info">No areas match your search.</Alert>;
  }
  return <DomainsGrid page={page} />;
}

function emptyTitle(filter: string, isAdmin: boolean): string {
  if (filter === "nice") return "No NICE areas yet";
  if (isAdmin) return "No areas yet";
  return "No areas match this filter";
}

function emptyBody(filter: string, isAdmin: boolean): string {
  if (filter === "nice") return "Run a guideline sync to add them.";
  if (isAdmin) return "Create one to get started.";
  return "Try a different source filter.";
}

function DomainsGrid({ page }: { page: DomainsList }) {
  return (
    <Box
      data-testid="domains-grid"
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(3, 1fr)" },
        gap: 2,
      }}
    >
      {page.filtered.map((d, i) => (
        <DomainCard
          key={d.id}
          domain={d}
          index={i}
          canEdit={page.isPlatformAdmin}
          onNavigate={(id) => page.router.push(`/settings/domains/${id}`)}
          onEdit={page.openEdit}
          onDelete={page.setDeleteTarget}
          onTestInLab={(domain) =>
            page.router.push(`/admin/knowledge?tab=validation-lab&domain_id=${domain.id}`)
          }
        />
      ))}
    </Box>
  );
}
