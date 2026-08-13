/**
 * Context Rules -- category cards. Details open in a 16:9 dialog.
 *
 * Atlas trace:
 *   Implements: DO-CFA1ED55
 *   DI: DI-340279C1
 */
"use client";

import AddIcon from "@mui/icons-material/Add";
import DownloadIcon from "@mui/icons-material/Download";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Grid from "@mui/material/Grid";
import Stack from "@mui/material/Stack";
import {
  EmptyState,
  FilterBar,
  SkeletonList,
  ToolbarActions,
} from "@leo/design-system";
import ConfirmDialog from "@/components/ConfirmDialog";

import ContextAddDialog from "./ContextAddDialog";
import ContextCategoryCard from "./ContextCategoryCard";
import ContextCategoryDialog from "./ContextCategoryDialog";
import { categoryCopyFor } from "./categoryCopy";
import type { ContextRule, FilterView } from "./types";
import { useContextRulesPage } from "./useContextRulesPage";

function sourceChips(
  sourceFilter: FilterView,
  onSourceChange: (value: FilterView) => void,
) {
  return [
    {
      id: "all",
      label: "All",
      active: sourceFilter === "all",
      onToggle: () => onSourceChange("all"),
    },
    {
      id: "builtin",
      label: "Built-in",
      active: sourceFilter === "builtin",
      onToggle: () => onSourceChange("builtin"),
    },
    {
      id: "custom",
      label: "Added",
      active: sourceFilter === "custom",
      onToggle: () => onSourceChange("custom"),
    },
  ];
}

function ContextRulesToolbar({
  search,
  sourceFilter,
  exporting,
  loading,
  canExport,
  onSearchChange,
  onSourceChange,
  onExport,
  onAdd,
}: {
  search: string;
  sourceFilter: FilterView;
  exporting: boolean;
  loading: boolean;
  canExport: boolean;
  onSearchChange: (value: string) => void;
  onSourceChange: (value: FilterView) => void;
  onExport: () => void;
  onAdd: () => void;
}) {
  return (
    <Stack direction="row" spacing={1.5} sx={{ mb: 2.5, flexWrap: "wrap" }} alignItems="center">
      <Box sx={{ flex: 1, minWidth: 240 }}>
        <FilterBar
          search={search}
          onSearchChange={onSearchChange}
          searchPlaceholder="Search phrases..."
          aria-label="Search context rules"
          chips={sourceChips(sourceFilter, onSourceChange)}
        />
      </Box>
      <ToolbarActions
        actions={[
          {
            id: "export-pdf",
            label: exporting ? "Exporting" : "Export PDF",
            icon: <DownloadIcon fontSize="small" />,
            variant: "secondary",
            onClick: onExport,
            disabled: exporting || loading || !canExport,
            loading: exporting,
          },
          {
            id: "add-rule",
            label: "Add rule",
            icon: <AddIcon fontSize="small" />,
            variant: "primary",
            onClick: onAdd,
          },
        ]}
      />
    </Stack>
  );
}

function CategoryCardGrid({
  keys,
  filtered,
  onOpen,
}: {
  keys: string[];
  filtered: ContextRule[];
  onOpen: (key: string, first?: ContextRule | null) => void;
}) {
  return (
    <Grid container spacing={2}>
      {keys.map((key, index) => {
        const rules = filtered.filter((rule) => rule.category === key);
        return (
          <Grid size={{ xs: 12, sm: 6, md: 4 }} key={key}>
            <ContextCategoryCard
              copy={categoryCopyFor(key)}
              rules={rules}
              index={index}
              onOpen={() => onOpen(key, rules[0] ?? null)}
            />
          </Grid>
        );
      })}
    </Grid>
  );
}

function ContextRulesBody({ page }: { page: ReturnType<typeof useContextRulesPage> }) {
  if (page.loading) return <SkeletonList rows={4} />;
  if (page.visibleKeys.length === 0) {
    return (
      <EmptyState
        icon={<AccountTreeOutlinedIcon />}
        title={page.rules.length === 0 ? "No context rules yet" : "No rules match"}
        body={
          page.rules.length === 0
            ? "Built-in phrases run automatically. Add a rule here to teach LEO a new trigger."
            : "Try a different search or filter."
        }
      />
    );
  }
  return (
    <CategoryCardGrid
      keys={page.visibleKeys}
      filtered={page.filtered}
      onOpen={page.openCategory}
    />
  );
}

function ContextRulesDialogs({ page }: { page: ReturnType<typeof useContextRulesPage> }) {
  const categoryRules = page.filtered.filter(
    (rule) => rule.category === page.openCopy?.key,
  );
  return (
    <>
      {page.openCopy && (
        <ContextCategoryDialog
          copy={page.openCopy}
          rules={categoryRules}
          selectedRule={page.selectedRule}
          onSelect={page.selectRule}
          onClose={page.closeCategory}
          onDeactivate={page.setDeactivateTarget}
        />
      )}
      <ContextAddDialog
        open={page.adding}
        saving={page.saving}
        error={page.saveError}
        onClose={page.cancelAdd}
        onSave={page.handleAdd}
      />
      {page.deactivateTarget ? (
        <ConfirmDialog
          title="Deactivate context rule?"
          body={`This will stop LEO using the phrase '${page.deactivateTarget.literal}' as a cue.`}
          confirmLabel="Deactivate"
          variant="danger"
          onConfirm={() => {
            if (page.deactivateTarget?.rule_id) {
              page.handleDeactivate(page.deactivateTarget.rule_id);
            }
            page.setDeactivateTarget(null);
          }}
          onCancel={() => page.setDeactivateTarget(null)}
        />
      ) : null}
    </>
  );
}

export default function ContextRulesPage() {
  const page = useContextRulesPage();
  return (
    <Box>
      <ContextRulesToolbar
        search={page.search}
        sourceFilter={page.sourceFilter}
        exporting={page.exporting}
        loading={page.loading}
        canExport={page.filtered.length > 0}
        onSearchChange={page.setSearch}
        onSourceChange={page.setSourceFilter}
        onExport={page.handleExportPdf}
        onAdd={page.startAdd}
      />
      {page.error ? (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => page.setError(null)}>
          {page.error}
        </Alert>
      ) : null}
      <ContextRulesBody page={page} />
      <ContextRulesDialogs page={page} />
    </Box>
  );
}
