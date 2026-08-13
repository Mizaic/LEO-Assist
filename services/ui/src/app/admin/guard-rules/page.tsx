/**
 * Pipeline Guards -- configurable NerGuardRule editor.
 *
 * Compact family cards. Details open in a dialog.
 *
 * Atlas trace:
 *   Implements: DO-6413D5BC (configurable guard rule conversions)
 *   DI: DI-34712A9A
 */
"use client";

import type { ReactNode } from "react";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Grid from "@mui/material/Grid";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import {
  EmptyState,
  FilterBar,
  ToolbarActions,
} from "@leo/design-system";

import GuardEditorPanel from "./GuardEditorPanel";
import GuardFamilyCard from "./GuardFamilyCard";
import GuardFamilyDialog from "./GuardFamilyDialog";
import {
  GUARD_FAMILIES,
  GUARD_FAMILY_COPY,
  RULE_TYPE_OPTIONS_BY_FAMILY,
} from "./guardFamilyCopy";
import type { NerGuardRule } from "./types";
import { useGuardRulesPage } from "./useGuardRulesPage";

function GuardRulesToolbar({
  search,
  familyFilter,
  onSearchChange,
  onFamilyChange,
  onAdd,
}: {
  search: string;
  familyFilter: string;
  onSearchChange: (value: string) => void;
  onFamilyChange: (value: string) => void;
  onAdd: () => void;
}) {
  return (
    <Stack direction="row" spacing={1.5} sx={{ mb: 2.5, flexWrap: "wrap" }} alignItems="center">
      <Box sx={{ flex: 1, minWidth: 240 }}>
        <FilterBar
          search={search}
          onSearchChange={onSearchChange}
          searchPlaceholder="Search patterns..."
          aria-label="Search guard rules"
          chips={GUARD_FAMILIES.map((family) => ({
            id: family.value,
            label: family.label,
            active: familyFilter === family.value,
            onToggle: () => onFamilyChange(family.value),
          }))}
        />
      </Box>
      <ToolbarActions
        actions={[{
          id: "add-rule",
          label: "Add rule",
          icon: <AddIcon fontSize="small" />,
          variant: "primary",
          onClick: onAdd,
        }]}
      />
    </Stack>
  );
}

function typeOptionsFor(rule: NerGuardRule | null, familyFilter: string) {
  if (rule) {
    return RULE_TYPE_OPTIONS_BY_FAMILY[rule.family]
      ?? [{ value: rule.rule_type, label: rule.rule_type }];
  }
  if (familyFilter !== "all") return RULE_TYPE_OPTIONS_BY_FAMILY[familyFilter] ?? [];
  return [{ value: "safety_netting", label: "Safety netting" }];
}

function FamilyCardGrid({
  cards,
  filtered,
  onOpen,
}: {
  cards: string[];
  filtered: NerGuardRule[];
  onOpen: (key: string, firstRule?: NerGuardRule | null) => void;
}) {
  return (
    <Grid container spacing={2}>
      {cards.map((key, index) => (
        <Grid size={{ xs: 12, sm: 6, md: 4 }} key={key}>
          <GuardFamilyCard
            copy={GUARD_FAMILY_COPY[key]}
            rules={filtered.filter((rule) => rule.family === key)}
            index={index}
            onOpen={() => onOpen(key, filtered.find((rule) => rule.family === key))}
          />
        </Grid>
      ))}
    </Grid>
  );
}

function AddRuleDialog({
  open,
  onClose,
  editor,
}: {
  open: boolean;
  onClose: () => void;
  editor: ReactNode;
}) {
  if (!open) return null;
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pr: 6 }}>
        Add guard rule
        <IconButton
          aria-label="Close"
          onClick={onClose}
          sx={{ position: "absolute", right: 8, top: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>{editor}</DialogContent>
    </Dialog>
  );
}

function boundEditor(page: ReturnType<typeof useGuardRulesPage>) {
  return (
    <GuardEditorPanel
      selectedRule={page.selectedRule}
      addingNew={page.addingNew}
      ruleTypeOptions={typeOptionsFor(
        page.selectedRule,
        page.openFamilyKey ?? page.familyFilter,
      )}
      saving={page.saving}
      onSave={page.handleSave}
      onCancel={page.clearSelection}
    />
  );
}

export default function GuardRulesPage() {
  const page = useGuardRulesPage();
  const editor = boundEditor(page);
  return (
    <Box>
      <GuardRulesToolbar
        search={page.search}
        familyFilter={page.familyFilter}
        onSearchChange={page.setSearch}
        onFamilyChange={page.setFamilyFilter}
        onAdd={page.startAdd}
      />
      {page.cards.length === 0 ? (
        <EmptyState
          icon={<ShieldOutlinedIcon />}
          title={page.rules.length === 0 ? "No guard rules yet" : "No rules match"}
          body={
            page.rules.length === 0
              ? "Built-in guards run automatically. Add a rule here to extend a guard without a code change."
              : "Try a different search or guard family."
          }
        />
      ) : (
        <FamilyCardGrid cards={page.cards} filtered={page.filtered} onOpen={page.openFamily} />
      )}
      {page.openCopy && (
        <GuardFamilyDialog
          copy={page.openCopy}
          rules={page.filtered.filter((rule) => rule.family === page.openCopy?.key)}
          selectedRule={page.selectedRule}
          onSelect={page.selectRule}
          onClose={page.closeFamily}
          editor={page.selectedRule ? editor : null}
        />
      )}
      <AddRuleDialog open={page.addingNew} onClose={page.cancelAdd} editor={editor} />
    </Box>
  );
}
