/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

/** Rolodex browser for Validation Lab test patients. Atlas: DI-43E908C6 / DI-020F98AE / DO-158BE606 */

import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ConfirmDialog from "@/components/ConfirmDialog";
import {
  caseSearchHaystack,
  caseTags,
  collectTagUniverse,
  sortCasesNaturally,
} from "./caseCardMeta";
import type { LabCase } from "./labApi";
import TestPatientCard from "./TestPatientCard";
import TestPatientRolodexFilters, {
  type GoldFilter,
  type ScenarioFilter,
  type TypeFilter,
} from "./TestPatientRolodexFilters";
import {
  allSelected,
  clearSelection,
  pruneSelection,
  someSelected,
  toggleId,
} from "./testPatientSelection";

interface Props {
  cases: LabCase[];
  selectedId: string;
  busy?: boolean;
  testingCaseId?: string;
  onSelect: (caseId: string) => void;
  onViewPatient: (patientId: string) => void;
  onTest: (caseId: string) => Promise<void>;
  onTestMany: (caseIds: string[]) => Promise<void>;
  onRename: (caseId: string, title: string) => Promise<void>;
  onDelete: (caseId: string) => Promise<void>;
  onDeleteMany: (caseIds: string[]) => Promise<void>;
}

function deleteConfirmCopy(ids: string[], cases: LabCase[]): {
  title: string;
  body: string;
  confirmLabel: string;
} {
  if (ids.length === 1) {
    const c = cases.find((item) => item.id === ids[0]);
    const label = c?.title || ids[0];
    return {
      title: "Delete test patient?",
      body: `This permanently removes "${label}" and its synthetic patient graph.`,
      confirmLabel: "Delete test patient",
    };
  }
  return {
    title: "Delete selected test patients?",
    body: `This permanently removes ${ids.length} test patients and their synthetic patient graphs.`,
    confirmLabel: `Delete ${ids.length} patients`,
  };
}

export default function TestPatientRolodex({
  cases,
  selectedId,
  busy = false,
  testingCaseId = "",
  onSelect,
  onViewPatient,
  onTest,
  onTestMany,
  onRename,
  onDelete,
  onDeleteMany,
}: Props) {
  const [query, setQuery] = useState("");
  const [scenarioFilter, setScenarioFilter] = useState<ScenarioFilter>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [goldFilter, setGoldFilter] = useState<GoldFilter>("all");
  const [tagFilter, setTagFilter] = useState("");
  const [editingId, setEditingId] = useState<string>("");
  const [editTitle, setEditTitle] = useState("");
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [pendingDeleteIds, setPendingDeleteIds] = useState<string[] | null>(
    null,
  );

  const tagOptions = useMemo(() => collectTagUniverse(cases), [cases]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = cases.filter((c) => {
      if (scenarioFilter !== "all" && (c.scenario_type || "generic") !== scenarioFilter) {
        return false;
      }
      if (typeFilter !== "all" && (c.case_type || "referral") !== typeFilter) {
        return false;
      }
      if (goldFilter === "gold" && !c.has_gold) return false;
      if (goldFilter === "no_gold" && c.has_gold) return false;
      if (tagFilter && !caseTags(c).includes(tagFilter)) return false;
      if (!q) return true;
      return caseSearchHaystack(c).includes(q);
    });
    return sortCasesNaturally(matched);
  }, [cases, query, scenarioFilter, typeFilter, goldFilter, tagFilter]);

  const filteredIds = useMemo(() => filtered.map((c) => c.id), [filtered]);

  useEffect(() => {
    setCheckedIds((prev) => pruneSelection(prev, cases.map((c) => c.id)));
  }, [cases]);

  const allVisibleChecked = allSelected(filteredIds, checkedIds);
  const someVisibleChecked = someSelected(filteredIds, checkedIds);

  function toggleSelectAllVisible() {
    if (allVisibleChecked) {
      setCheckedIds((prev) => {
        const next = new Set(prev);
        for (const id of filteredIds) next.delete(id);
        return next;
      });
      return;
    }
    setCheckedIds((prev) => {
      const next = new Set(prev);
      for (const id of filteredIds) next.add(id);
      return next;
    });
  }

  async function confirmPendingDelete() {
    if (!pendingDeleteIds?.length) return;
    const ids = pendingDeleteIds;
    setPendingDeleteIds(null);
    if (ids.length === 1) await onDelete(ids[0]);
    else await onDeleteMany(ids);
    setCheckedIds(clearSelection());
  }

  const confirmCopy = pendingDeleteIds
    ? deleteConfirmCopy(pendingDeleteIds, cases)
    : null;

  return (
    <Box data-testid="validation-lab-rolodex">
      <Typography variant="h6" component="h2" sx={{ mb: 1 }}>
        Test patients
      </Typography>
      <TestPatientRolodexFilters
        query={query}
        onQueryChange={setQuery}
        scenarioFilter={scenarioFilter}
        onScenarioFilterChange={setScenarioFilter}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
        goldFilter={goldFilter}
        onGoldFilterChange={setGoldFilter}
        tagFilter={tagFilter}
        onTagFilterChange={setTagFilter}
        tagOptions={tagOptions}
      />

      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        alignItems={{ xs: "stretch", sm: "center" }}
        justifyContent="space-between"
        sx={{ mb: 1 }}
      >
        <Typography variant="caption" color="text.secondary">
          Showing {filtered.length} of {cases.length}
          {checkedIds.size > 0 ? ` · ${checkedIds.size} selected` : ""}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <FormControlLabel
            sx={{ mr: 0 }}
            control={
              <Checkbox
                size="small"
                checked={allVisibleChecked}
                indeterminate={!allVisibleChecked && someVisibleChecked}
                disabled={busy || filtered.length === 0}
                onChange={toggleSelectAllVisible}
                inputProps={{ "aria-label": "Select all visible test patients" }}
                data-testid="validation-lab-select-all"
              />
            }
            label="Select all"
          />
          <Button
            size="small"
            variant="contained"
            disabled={busy || checkedIds.size === 0}
            onClick={() => {
              const ids = Array.from(checkedIds);
              void onTestMany(ids).then(() => setCheckedIds(clearSelection()));
            }}
            data-testid="validation-lab-test-selected"
          >
            {checkedIds.size > 0
              ? `Test selected (${checkedIds.size})`
              : "Test selected"}
          </Button>
          <Button
            size="small"
            color="error"
            variant="outlined"
            disabled={busy || checkedIds.size === 0}
            onClick={() => setPendingDeleteIds(Array.from(checkedIds))}
            data-testid="validation-lab-delete-selected"
          >
            Delete selected
          </Button>
        </Stack>
      </Stack>

      <Stack spacing={1} data-testid="validation-lab-case-list">
        {filtered.length === 0 && (
          <Typography variant="body2" color="text.secondary">
            No test patients match. Clear search/filters or create a new one.
          </Typography>
        )}
        {filtered.map((c) => (
          <TestPatientCard
            key={c.id}
            caseItem={c}
            selected={c.id === selectedId}
            checked={checkedIds.has(c.id)}
            renaming={editingId === c.id}
            testing={testingCaseId === c.id}
            busy={busy}
            editTitle={editTitle}
            onEditTitle={setEditTitle}
            onToggleCheck={() =>
              setCheckedIds((prev) => toggleId(prev, c.id))
            }
            onSelect={() => onSelect(c.id)}
            onStartRename={() => {
              setEditingId(c.id);
              setEditTitle(c.title || "");
            }}
            onCancelRename={() => {
              setEditingId("");
              setEditTitle("");
            }}
            onSaveRename={() => {
              void onRename(c.id, editTitle.trim()).then(() => {
                setEditingId("");
                setEditTitle("");
              });
            }}
            onViewPatient={() => {
              if (c.patient_id) onViewPatient(c.patient_id);
            }}
            onTest={() => void onTest(c.id)}
            onDelete={() => setPendingDeleteIds([c.id])}
            onTagClick={setTagFilter}
          />
        ))}
      </Stack>

      {confirmCopy && pendingDeleteIds ? (
        <ConfirmDialog
          title={confirmCopy.title}
          body={confirmCopy.body}
          confirmLabel={confirmCopy.confirmLabel}
          variant="danger"
          onConfirm={() => void confirmPendingDelete()}
          onCancel={() => setPendingDeleteIds(null)}
        />
      ) : null}
    </Box>
  );
}
