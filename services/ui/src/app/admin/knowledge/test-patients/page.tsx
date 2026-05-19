/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2C03CA0E
 *   DI: DI-3F771AFB
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2C03CA0E")
 */
"use client";

/**
 * Knowledge > Test Patients -- the centralised test patient library.
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - StatHero: one tile per aspect (All / Reading notes / Patient
 *     story / Rule checks / SBAR handover).
 *   - SegmentedTabs: aspect filter, drives the row query.
 *   - ToolbarActions: Build / Copy from a real patient (Phase A:
 *     surfaced but disabled until Phase B-D land per-aspect builders).
 *   - DataGridCard: list of saved test patients with Source / Aspect
 *     chips, age + sex, created_by, and a per-row Delete action.
 *
 * Phase A scope (this PR):
 *   - Aspect filter + count tiles wired to /test-patients endpoints.
 *   - Table of saved test patients with the test_ prefix and aspect
 *     chip clearly visible.
 *
 * The legacy /admin/guidance/test-patients route is removed in this
 * same change set; the supporting dialog modules under
 * services/ui/src/app/admin/guidance/test-patients/ are still the
 * source of truth for the Guidelines aspect and will be re-mounted
 * here in Phase B.
 *
 * Atlas IDs: UN-50102672, DI-7625C251, DO-EE2C2EA1, R-8C0CC94B,
 * VT-5BDFE5F7.
 *
 * Audience (UK reading age 11): all visible copy is plain English.
 * Technical concepts (aspect, replay) are translated in helper text.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import FileCopyOutlinedIcon from "@mui/icons-material/FileCopyOutlined";
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";

import {
  DataGridCard,
  SegmentedTabs,
  StatHero,
  ToolbarActions,
  type DataGridColumn,
  type StatTile,
  type ToolbarAction,
} from "@leo/design-system";

import {
  ASPECT_HINT,
  ASPECT_LABEL,
  ASPECT_VALUES,
  TRIAGE_OUTCOME_HINT,
  TRIAGE_OUTCOME_LABEL,
  TRIAGE_OUTCOME_VALUES,
  type AspectCounts,
  type AspectFilter,
  type ReplayReport,
  type TestPatientRow,
  type TriageOutcome,
  type TriageOutcomeCounts,
} from "./types";
import {
  deleteTestPatient,
  getAspectCounts,
  getBitmapStatus,
  getTriageOutcomeCounts,
  listGuidanceRules,
  listTestPatients,
  replay,
} from "./api";
import BuildPatientDialog from "./BuildPatientDialog";
import CopyFromRealDialog from "./CopyFromRealDialog";
import ScaffoldFromRuleDialog from "./ScaffoldFromRuleDialog";
import ScaffoldFromScenarioDialog from "./ScaffoldFromScenarioDialog";
import EditTestPatientDrawer from "./editor/EditTestPatientDrawer";
import ReplayResultsDialog from "./replay/ReplayResultsDialog";
import RulesetNotCompiledBanner from "./replay/RulesetNotCompiledBanner";
import ConfirmDialog from "@/components/ConfirmDialog";

const ZERO_COUNTS: AspectCounts = {
  all: 0,
  nlp: 0,
  episodes: 0,
  guidelines: 0,
  summarisation: 0,
};

const ZERO_TRIAGE_COUNTS: TriageOutcomeCounts = {
  "2ww": 0,
  urgent: 0,
  routine: 0,
  no_rule_fired: 0,
  evaluator_outage: 0,
  unset: 0,
};

// The triage chip group only makes sense for the SBAR / referral-
// triage aspect. We also show it on "all" so a reviewer sweeping
// the whole library can still slice by 2ww / urgent / routine.
function showsTriageFilter(aspect: AspectFilter): boolean {
  return aspect === "summarisation" || aspect === "all";
}

// Which aspects can be replayed against the production / sandbox
// roaring-bitmap ruleset today. Guidelines and SBAR / referral
// triage carry rule-firing expectations (EXPECTED_RESULT or
// ExpectedSBAR.matched_rule_ids) that the bitmap evaluator can
// score against. NLP and Episodes do not have a one-click rerun
// endpoint yet -- the per-row Test button is disabled with a
// tooltip explaining this so reviewers can't fire a no-op replay.
function aspectSupportsReplay(aspect: AspectFilter | string): boolean {
  return aspect === "guidelines" || aspect === "summarisation";
}

const REPLAY_UNSUPPORTED_HINT =
  "Replay only works for Guidelines and SBAR / referral triage today. " +
  "NLP and Episodes patients do not yet have a one-click rerun.";

function buildStats(counts: AspectCounts): StatTile[] {
  return ASPECT_VALUES.map((key) => {
    const value = counts[key as keyof AspectCounts] ?? 0;
    const tone: StatTile["tone"] =
      key === "all" ? "neutral" : value > 0 ? "positive" : "neutral";
    return {
      id: key,
      label: ASPECT_LABEL[key],
      value,
      hint: ASPECT_HINT[key],
      tone,
    };
  });
}

function sourceChipLabel(row: TestPatientRow): string {
  if (row.generation_source === "cloned") return "Copied from real";
  if (row.generation_source === "manual") return "Built by hand";
  return row.generation_source ?? "-";
}

function ageSex(row: TestPatientRow): string {
  const age = row.age != null ? `${row.age}y` : "-";
  const sex = row.sex ?? "-";
  return `${age} / ${sex}`;
}

// LONG FUNCTION: page orchestrates fetch, filter, and 4 callbacks.
// Splitting further would scatter the load/refresh state across files.
export default function TestPatientLibraryKnowledgeTab() {
  // The rule editor's "Try it on real patients" panel deep-links here
  // with ?rule_id=<id> so the reviewer lands on the same library
  // pre-filtered to only the patients that exercise their rule. The
  // tab key is preserved by the parent KnowledgePage; we only own the
  // rule_id param here.
  const router = useRouter();
  const searchParams = useSearchParams();
  const ruleIdFilter = searchParams.get("rule_id");

  const [aspect, setAspect] = useState<AspectFilter>("all");
  const [triageOutcome, setTriageOutcome] = useState<TriageOutcome>("all");
  const [counts, setCounts] = useState<AspectCounts>(ZERO_COUNTS);
  const [triageCounts, setTriageCounts] =
    useState<TriageOutcomeCounts>(ZERO_TRIAGE_COUNTS);
  const [rows, setRows] = useState<TestPatientRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [buildOpen, setBuildOpen] = useState(false);
  const [copyOpen, setCopyOpen] = useState(false);
  const [scaffoldOpen, setScaffoldOpen] = useState(false);
  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<TestPatientRow | null>(
    null,
  );
  // Replay state. Mirrors the rule editor's TestPatientsPanel so the
  // ReplayResultsDialog renders the exact same regression / pass /
  // drift breakdown reviewers already know from the rule editor.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [replayReport, setReplayReport] = useState<ReplayReport | null>(null);
  const [replayPatients, setReplayPatients] = useState<TestPatientRow[]>([]);
  const [replayOpen, setReplayOpen] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [runningRowId, setRunningRowId] = useState<string | null>(null);
  const [replayError, setReplayError] = useState<string | null>(null);
  const [notCompiled, setNotCompiled] = useState(false);
  // Rule lookup keyed by rule_id, used to translate raw rule_ids in
  // the replay dialog into the same friendly label the rule picker
  // uses (e.g. "1.1.5 Offer an urgent chest X-ray ..."). Lazy: we
  // only fetch on the first replay so the page mount stays cheap.
  const [rulesLookup, setRulesLookup] = useState<
    Record<string, { name?: string; recommendation_text?: string }>
  >({});

  const fetchAll = useCallback(() => {
    setLoading(true);
    setError(null);
    // The triage chip group only filters when the SBAR aspect is in
    // scope. Sending the param on the NLP / Episodes / Guidelines
    // aspects would hide every row (none of them have an
    // ExpectedSBAR), so we drop it client-side instead.
    const outcomeForList = showsTriageFilter(aspect) ? triageOutcome : "all";
    Promise.all([
      listTestPatients({
        aspect,
        triage_outcome: outcomeForList,
        rule_id: ruleIdFilter ?? undefined,
      }),
      getAspectCounts(),
      getTriageOutcomeCounts(),
    ])
      .then(([patientRows, aspectCounts, outcomeCounts]) => {
        setRows(patientRows);
        setCounts(aspectCounts);
        setTriageCounts(outcomeCounts);
      })
      .catch((exc: unknown) => {
        setError(
          exc instanceof Error
            ? exc.message
            : "Could not load the test patient library.",
        );
      })
      .finally(() => setLoading(false));
  }, [aspect, triageOutcome, ruleIdFilter]);

  const clearRuleFilter = useCallback(() => {
    const next = new URLSearchParams(searchParams.toString());
    next.delete("rule_id");
    const qs = next.toString();
    router.replace(`/admin/knowledge${qs ? `?${qs}` : ""}`);
  }, [router, searchParams]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll, refreshKey]);

  const handleDelete = useCallback((row: TestPatientRow) => {
    setPendingDelete(row);
  }, []);

  const confirmDelete = useCallback(async () => {
    const row = pendingDelete;
    if (!row) return;
    setPendingDelete(null);
    try {
      await deleteTestPatient(row.id);
      setRefreshKey((n) => n + 1);
    } catch (exc) {
      setError(
        exc instanceof Error
          ? exc.message
          : "Could not delete that test patient.",
      );
    }
  }, [pendingDelete]);

  // Drop the selection whenever the visible row set changes. Otherwise
  // a reviewer who selects 3 SBAR rows then switches to NLP would still
  // be carrying around three invisible selections that "Test selected"
  // would silently include.
  useEffect(() => {
    setSelectedIds(new Set());
  }, [aspect, triageOutcome, ruleIdFilter, refreshKey]);

  // Probe the production bitmap once on mount so the "no ruleset
  // compiled" banner can show even before the reviewer fires their
  // first replay. Cheap (cached server-side) and matches the rule
  // editor panel's UX.
  useEffect(() => {
    let cancelled = false;
    getBitmapStatus("global", "default")
      .then((status) => {
        if (cancelled) return;
        setNotCompiled(!status.active_version || status.rule_count === 0);
      })
      .catch(() => {
        // Best-effort: if the status endpoint is unreachable, the
        // replay-error path below still surfaces the missing ruleset.
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  // Lazy rule lookup. Fetches every rule in the active scope once
  // (~hundreds of rows, capped at 500 to match the rule picker) and
  // memoises the result. Each entry stores BOTH the curated short
  // ``name`` and the picker's ``display_label`` so the replay dialog
  // can render the same friendly label the user picked from
  // (e.g. "1.1.5 Offer an urgent chest X-ray ...") even when the
  // patient was scaffolded against a now-edited rule_id.
  const ensureRulesLookup = useCallback(async () => {
    if (Object.keys(rulesLookup).length > 0) return rulesLookup;
    try {
      const rules = await listGuidanceRules({ limit: 500 });
      const next: Record<
        string,
        { name?: string; recommendation_text?: string }
      > = {};
      for (const r of rules) {
        next[r.rule_id] = {
          name: r.display_label || r.name || undefined,
          recommendation_text: r.recommendation_text || undefined,
        };
      }
      setRulesLookup(next);
      return next;
    } catch {
      return rulesLookup;
    }
  }, [rulesLookup]);

  const runReplayFor = useCallback(
    async (patientsToTest: TestPatientRow[], runningId: string | null) => {
      // Drop NLP / Episodes rows -- the bitmap evaluator only knows
      // how to score guideline-firing expectations, so feeding it
      // anything else would either error or silently return zero
      // results. We surface the skip count to the reviewer instead
      // of failing the whole batch.
      const eligible = patientsToTest.filter((p) => aspectSupportsReplay(p.aspect));
      const skipped = patientsToTest.length - eligible.length;
      if (eligible.length === 0) {
        setReplayError(REPLAY_UNSUPPORTED_HINT);
        return;
      }
      setReplaying(true);
      setRunningRowId(runningId);
      setReplayError(null);
      try {
        // Kick off the rule-name fetch in parallel with the replay
        // so the dialog opens with friendly labels already in hand.
        const rulesPromise = ensureRulesLookup();
        const result = await replay({
          patient_ids: eligible.map((p) => p.id),
          scope_type: "global",
          scope_id: "default",
          persist_report: false,
        });
        await rulesPromise;
        setReplayReport(result);
        setReplayPatients(eligible);
        const looksUncompiled = (result.results || []).some((row) =>
          (row.error || "").toLowerCase().includes("no active ruleset"),
        );
        setNotCompiled(looksUncompiled);
        if (skipped > 0) {
          setReplayError(
            `Skipped ${skipped} patient${skipped === 1 ? "" : "s"} ` +
              "from NLP / Episodes -- they cannot be replayed yet.",
          );
        }
        setReplayOpen(true);
      } catch (exc) {
        const msg =
          exc instanceof Error ? exc.message : "Could not replay the patients.";
        if (msg.toLowerCase().includes("no active ruleset")) {
          setNotCompiled(true);
        } else {
          setReplayError(msg);
        }
      } finally {
        setReplaying(false);
        setRunningRowId(null);
      }
    },
    [ensureRulesLookup],
  );

  // Master-checkbox state derived from the visible rows + selection
  // set. Indeterminate when 1+ but not all visible rows are selected.
  const allSelected = useMemo(
    () => rows.length > 0 && rows.every((r) => selectedIds.has(r.id)),
    [rows, selectedIds],
  );
  const someSelected = useMemo(
    () => !allSelected && rows.some((r) => selectedIds.has(r.id)),
    [rows, selectedIds, allSelected],
  );

  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (rows.every((r) => prev.has(r.id)) && rows.length > 0) {
        return new Set();
      }
      return new Set(rows.map((r) => r.id));
    });
  }, [rows]);

  const toggleRow = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectedCount = selectedIds.size;
  const visibleEligibleCount = useMemo(
    () => rows.filter((r) => aspectSupportsReplay(r.aspect)).length,
    [rows],
  );

  const stats = useMemo(() => buildStats(counts), [counts]);

  const filterTabs = useMemo(
    () =>
      ASPECT_VALUES.map((value) => ({
        id: value,
        label: ASPECT_LABEL[value],
        count: counts[value as keyof AspectCounts] ?? 0,
      })),
    [counts],
  );

  const toolbarActions: ToolbarAction[] = useMemo(
    () => [
      {
        id: "scaffold-from-scenario",
        label: "Author from a scenario (AI)",
        icon: <AutoAwesomeOutlinedIcon fontSize="small" />,
        variant: "secondary",
        onClick: () => setScenarioOpen(true),
      },
      {
        id: "scaffold-from-rule",
        label: "Scaffold from a rule (AI)",
        icon: <AutoAwesomeOutlinedIcon fontSize="small" />,
        variant: "secondary",
        onClick: () => setScaffoldOpen(true),
      },
      {
        id: "build-patient",
        label: "Build a patient",
        icon: <AddIcon fontSize="small" />,
        variant: "secondary",
        onClick: () => setBuildOpen(true),
      },
      {
        id: "copy-from-real",
        label: "Copy from a real patient",
        icon: <FileCopyOutlinedIcon fontSize="small" />,
        variant: "primary",
        onClick: () => setCopyOpen(true),
      },
    ],
    [],
  );

  const columns: DataGridColumn<TestPatientRow>[] = useMemo(
    () => [
      {
        id: "select",
        header: (
          <Tooltip
            title={
              allSelected
                ? "Clear selection"
                : "Select every visible test patient"
            }
            arrow
          >
            <Checkbox
              size="small"
              data-testid="select-all-checkbox"
              checked={allSelected}
              indeterminate={someSelected}
              onChange={toggleAll}
              inputProps={{
                "aria-label": "Select all visible test patients",
              }}
            />
          </Tooltip>
        ),
        width: "44px",
        render: (row) => (
          <Checkbox
            size="small"
            data-testid={`select-row-${row.id}`}
            checked={selectedIds.has(row.id)}
            onChange={() => toggleRow(row.id)}
            inputProps={{
              "aria-label": `Select ${row.name}`,
            }}
          />
        ),
      },
      {
        id: "name",
        header: "Name",
        render: (row) => (
          <Box>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {row.name}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {row.id}
            </Typography>
          </Box>
        ),
      },
      {
        id: "aspect",
        header: "Part of AI",
        render: (row) => (
          <Chip
            size="small"
            label={ASPECT_LABEL[row.aspect]}
            color={row.aspect === "guidelines" ? "primary" : "default"}
            variant="outlined"
            sx={{ fontWeight: 500 }}
          />
        ),
        width: "180px",
      },
      {
        id: "source",
        header: "Source",
        render: (row) => (
          <Chip
            size="small"
            label={sourceChipLabel(row)}
            variant="outlined"
            sx={{ fontWeight: 500 }}
          />
        ),
        width: "180px",
      },
      {
        id: "demographics",
        header: "Age / sex",
        render: (row) => (
          <Typography variant="body2">{ageSex(row)}</Typography>
        ),
        width: "120px",
      },
      {
        id: "triage_outcome",
        header: "Triage outcome",
        render: (row) =>
          row.triage_outcome ? (
            <Tooltip title={TRIAGE_OUTCOME_HINT[row.triage_outcome]} arrow>
              <Chip
                size="small"
                variant="outlined"
                label={TRIAGE_OUTCOME_LABEL[row.triage_outcome]}
                color={
                  row.triage_outcome === "2ww"
                    ? "error"
                    : row.triage_outcome === "urgent"
                      ? "warning"
                      : row.triage_outcome === "evaluator_outage"
                        ? "warning"
                        : "default"
                }
                sx={{ fontWeight: 500 }}
              />
            </Tooltip>
          ) : (
            <Typography variant="caption" color="text.secondary">
              -
            </Typography>
          ),
        width: "180px",
      },
      {
        id: "created_by",
        header: "Built by",
        render: (row) => (
          <Typography variant="body2">{row.created_by || "-"}</Typography>
        ),
        width: "160px",
      },
      {
        id: "actions",
        header: "",
        align: "right",
        width: "160px",
        render: (row) => {
          const supportsReplay = aspectSupportsReplay(row.aspect);
          const rowReplaying = runningRowId === row.id;
          return (
            <Stack direction="row" spacing={0.5} justifyContent="flex-end">
              <Tooltip
                title={
                  supportsReplay
                    ? `Test ${row.name} against the live ruleset`
                    : REPLAY_UNSUPPORTED_HINT
                }
                arrow
              >
                <span>
                  <IconButton
                    size="small"
                    color="success"
                    onClick={() => runReplayFor([row], row.id)}
                    aria-label={`Test ${row.name} against the live ruleset`}
                    disabled={!supportsReplay || replaying}
                    data-testid={`test-now-${row.id}`}
                  >
                    {rowReplaying ? (
                      <CircularProgress size={16} color="inherit" />
                    ) : (
                      <PlayCircleOutlineIcon fontSize="small" />
                    )}
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip
                title={
                  row.aspect === "guidelines"
                    ? `Edit ${row.name} in the guideline editor`
                    : `Edit ${row.name}`
                }
                arrow
              >
                <span>
                  <IconButton
                    size="small"
                    onClick={() => setEditingId(row.id)}
                    aria-label={`Edit test patient ${row.name}`}
                    disabled={row.aspect === "guidelines"}
                  >
                    <EditOutlinedIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title={`Delete ${row.name}`} arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={() => handleDelete(row)}
                    aria-label={`Delete test patient ${row.name}`}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Stack>
          );
        },
      },
    ],
    [
      handleDelete,
      runReplayFor,
      runningRowId,
      replaying,
      selectedIds,
      allSelected,
      someSelected,
      toggleAll,
      toggleRow,
    ],
  );

  const emptyState = (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>
        No test patients saved for this view yet.
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Build one or copy a real patient to get started. Test patients
        always carry the test_ prefix so they cannot leak into clinical
        screens.
      </Typography>
    </Box>
  );

  return (
    <Box>
      <StatHero stats={stats} />

      {ruleIdFilter ? (
        <Alert
          severity="info"
          icon={false}
          sx={{ mb: 2 }}
          action={
            <Button
              size="small"
              color="inherit"
              onClick={clearRuleFilter}
              data-testid="clear-rule-filter"
            >
              Show all
            </Button>
          }
          data-testid="rule-filter-banner"
        >
          Showing only test patients linked to rule{" "}
          <strong>{ruleIdFilter}</strong>. This is the same view the rule
          editor uses on its "Try it on real patients" panel.
        </Alert>
      ) : null}

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
          tabs={filterTabs}
          value={aspect}
          onChange={(id) => {
            const next = id as AspectFilter;
            setAspect(next);
            if (!showsTriageFilter(next)) setTriageOutcome("all");
          }}
          aria-label="Filter test patients by AI aspect"
        />
        <ToolbarActions actions={toolbarActions} />
      </Box>

      {showsTriageFilter(aspect) ? (
        <Box
          sx={{ mb: 2 }}
          role="group"
          aria-label="Filter SBAR test patients by triage outcome"
        >
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mb: 0.75 }}
          >
            Triage outcome -- what the SBAR should recommend.
            NICE NG12 suspected-cancer fixtures sit under 2 week wait.
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }}>
            {TRIAGE_OUTCOME_VALUES.map((value) => {
              const selected = triageOutcome === value;
              const count =
                value === "all"
                  ? Object.values(triageCounts).reduce((a, b) => a + b, 0)
                  : triageCounts[value] ?? 0;
              return (
                <Tooltip key={value} title={TRIAGE_OUTCOME_HINT[value]} arrow>
                  <Chip
                    label={`${TRIAGE_OUTCOME_LABEL[value]} (${count})`}
                    size="small"
                    variant={selected ? "filled" : "outlined"}
                    color={selected ? "primary" : "default"}
                    onClick={() => setTriageOutcome(value)}
                    aria-pressed={selected}
                    data-testid={`triage-chip-${value}`}
                  />
                </Tooltip>
              );
            })}
          </Stack>
        </Box>
      ) : null}

      {replayError ? (
        <Alert
          severity="warning"
          sx={{ mb: 2 }}
          onClose={() => setReplayError(null)}
          data-testid="replay-warning"
        >
          {replayError}
        </Alert>
      ) : null}

      {notCompiled ? (
        <Box sx={{ mb: 2 }} data-testid="not-compiled-banner">
          <RulesetNotCompiledBanner
            scopeType="global"
            scopeId="default"
            sandbox={false}
            onCompileRequested={() => {
              setTimeout(() => {
                getBitmapStatus("global", "default")
                  .then((status) =>
                    setNotCompiled(
                      !status.active_version || status.rule_count === 0,
                    ),
                  )
                  .catch(() => undefined);
              }, 4000);
            }}
          />
        </Box>
      ) : null}

      {/*
       * Test action strip. Lives ABOVE the data grid so a reviewer
       * can replay the visible cohort without scrolling. Mirrors the
       * rule editor's "Try it on real patients" panel: same replay
       * endpoint, same ReplayResultsDialog, so the reviewer never has
       * to learn two flows.
       */}
      <Stack
        direction="row"
        spacing={1}
        sx={{ mb: 1.5, flexWrap: "wrap", rowGap: 1, alignItems: "center" }}
        data-testid="test-action-strip"
      >
        <Tooltip
          title={
            selectedCount === 0
              ? "Tick a box on the left of any row to enable this."
              : `Test ${selectedCount} selected patient${
                  selectedCount === 1 ? "" : "s"
                } against the live ruleset.`
          }
          arrow
        >
          <span>
            <Button
              size="small"
              variant="contained"
              color="success"
              startIcon={
                replaying && runningRowId === null ? (
                  <CircularProgress size={14} color="inherit" />
                ) : (
                  <PlayCircleOutlineIcon fontSize="small" />
                )
              }
              disabled={selectedCount === 0 || replaying}
              onClick={() => {
                const picked = rows.filter((r) => selectedIds.has(r.id));
                runReplayFor(picked, null);
              }}
              data-testid="test-selected-button"
              aria-label={`Test ${selectedCount} selected test patients against the live ruleset`}
            >
              {replaying && runningRowId === null
                ? "Testing..."
                : `Test selected (${selectedCount})`}
            </Button>
          </span>
        </Tooltip>
        <Tooltip
          title={
            visibleEligibleCount === 0
              ? "No replay-able patients in this view."
              : `Replay every visible Guidelines / SBAR test patient (${visibleEligibleCount}).`
          }
          arrow
        >
          <span>
            <Button
              size="small"
              variant="outlined"
              color="success"
              startIcon={<PlayCircleOutlineIcon fontSize="small" />}
              disabled={visibleEligibleCount === 0 || replaying}
              onClick={() => runReplayFor(rows, null)}
              data-testid="test-all-button"
              aria-label="Test all visible test patients against the live ruleset"
            >
              {`Test all visible (${visibleEligibleCount})`}
            </Button>
          </span>
        </Tooltip>
        <Typography variant="caption" color="text.secondary">
          Replay runs against the live (production) ruleset and never
          changes saved patients.
        </Typography>
      </Stack>

      {loading ? (
        <Stack alignItems="center" sx={{ pt: 6 }}>
          <CircularProgress size={28} />
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mt: 1 }}
          >
            Loading test patients...
          </Typography>
        </Stack>
      ) : (
        <DataGridCard<TestPatientRow>
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          emptyState={emptyState}
        />
      )}

      <BuildPatientDialog
        open={buildOpen}
        initialAspect={aspect}
        onClose={() => setBuildOpen(false)}
        onCreated={() => setRefreshKey((n) => n + 1)}
      />

      <CopyFromRealDialog
        open={copyOpen}
        initialAspect={aspect}
        onClose={() => setCopyOpen(false)}
        onCloned={() => setRefreshKey((n) => n + 1)}
      />

      <ScaffoldFromRuleDialog
        open={scaffoldOpen}
        initialAspect={aspect}
        onClose={() => setScaffoldOpen(false)}
        onScaffolded={(newPatientId) => {
          setRefreshKey((n) => n + 1);
          setEditingId(newPatientId);
        }}
      />

      <ScaffoldFromScenarioDialog
        open={scenarioOpen}
        initialAspect={aspect}
        onClose={() => setScenarioOpen(false)}
        onScaffolded={(newPatientId) => {
          setRefreshKey((n) => n + 1);
          setEditingId(newPatientId);
        }}
      />

      <EditTestPatientDrawer
        patientId={editingId}
        open={editingId !== null}
        onClose={() => setEditingId(null)}
        onSaved={() => setRefreshKey((n) => n + 1)}
      />

      {pendingDelete ? (
        <ConfirmDialog
          title="Delete this test patient?"
          body={`This will remove "${pendingDelete.name}" from the test patient library. You cannot undo this.`}
          confirmLabel="Delete"
          cancelLabel="Keep"
          variant="danger"
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        />
      ) : null}

      <ReplayResultsDialog
        open={replayOpen}
        onClose={() => setReplayOpen(false)}
        report={replayReport}
        patients={replayPatients}
        rules={rulesLookup}
        mode="live"
      />
    </Box>
  );
}
