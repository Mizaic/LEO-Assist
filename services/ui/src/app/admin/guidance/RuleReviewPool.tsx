/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

import { useEffect, useMemo, useState } from "react";
import Autocomplete from "@mui/material/Autocomplete";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Pagination from "@mui/material/Pagination";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import ExpandMoreRoundedIcon from "@mui/icons-material/ExpandMoreRounded";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";

import { EmptyState, FilterBar, SkeletonList } from "@leo/design-system";

import { RuleAccordionCard } from "./RuleReviewCard";
import { STRENGTH_LABELS } from "./EditRuleDialog/copy";
import type { Rule, RuleStatusFilter } from "./ruleReviewTypes";
import { sortRulesForStatus } from "./ruleReviewHelpers";
import {
  DEFAULT_RULE_PAGE_SIZE,
  collectGuidelineIds,
  collectStrengths,
  filterRulesByGuideline,
  filterRulesByStrength,
  paginateRules,
  ruleMatchesSearch,
} from "./ruleReviewPoolUtils";

const ALL = "all";

function strengthLabel(value: string): string {
  return STRENGTH_LABELS.find((row) => row.value === value)?.label ?? value.replace(/_/g, " ");
}

export interface RuleReviewPoolProps {
  poolId: "pending" | "approved" | "excluded" | "superseded";
  title: string;
  helper: string;
  statusFilter: RuleStatusFilter;
  rules: Rule[];
  loading: boolean;
  loadCap?: number;
  expandedRules: Record<string, boolean>;
  busy: string | null;
  showApproveAll?: boolean;
  onApproveAll?: () => void;
  onToggle: (ruleId: string) => void;
  onEdit: (rule: Rule) => void;
  onApprove?: (rule: Rule) => void;
  onReject?: (rule: Rule) => void;
  /** Pools start collapsed so the review page stays scannable. */
  defaultOpen?: boolean;
}

function emptyCopy(poolId: RuleReviewPoolProps["poolId"]): { title: string; body: string } {
  if (poolId === "pending") {
    return {
      title: "No rules awaiting review",
      body: "Load a guideline above, then generate rules to start reviewing.",
    };
  }
  if (poolId === "excluded") {
    return {
      title: "No excluded recommendations yet",
      body: "Confirm 'no rule needed', reject a pending rule, or exclude an approved rule to fill this list. Excluded items are not compiled live.",
    };
  }
  if (poolId === "superseded") {
    return {
      title: "No superseded rules yet",
      body: "Older versions appear here after you edit and save a rule.",
    };
  }
  return {
    title: "No approved rules yet",
    body: "No approved rules match your search. Approve pending rules to fill this pool.",
  };
}

export default function RuleReviewPool({
  poolId,
  title,
  helper,
  statusFilter,
  rules,
  loading,
  loadCap = 200,
  expandedRules,
  busy,
  showApproveAll = false,
  onApproveAll,
  onToggle,
  onEdit,
  onApprove,
  onReject,
  defaultOpen = false,
}: RuleReviewPoolProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [search, setSearch] = useState("");
  const [guidelineFilter, setGuidelineFilter] = useState(ALL);
  const [strengthFilter, setStrengthFilter] = useState(ALL);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_RULE_PAGE_SIZE);

  const guidelineOptions = useMemo(() => collectGuidelineIds(rules), [rules]);
  const strengthOptions = useMemo(() => collectStrengths(rules), [rules]);

  const filteredRules = useMemo(() => {
    let next = rules.filter((rule) => ruleMatchesSearch(rule, search));
    next = filterRulesByGuideline(next, guidelineFilter);
    next = filterRulesByStrength(next, strengthFilter);
    return sortRulesForStatus(next, statusFilter);
  }, [rules, search, guidelineFilter, strengthFilter, statusFilter]);

  const pagination = useMemo(
    () => paginateRules(filteredRules, page, pageSize),
    [filteredRules, page, pageSize],
  );

  useEffect(() => {
    setPage(1);
  }, [search, guidelineFilter, strengthFilter, pageSize, rules.length]);

  useEffect(() => {
    if (page > pagination.totalPages) setPage(pagination.totalPages);
  }, [page, pagination.totalPages]);

  const { title: emptyTitle, body: emptyBody } = emptyCopy(poolId);

  return (
    <Box
      component="section"
      aria-labelledby={`${poolId}-pool-title`}
      data-testid={`rule-pool-${poolId}`}
      data-tour={poolId === "pending" ? "cg-04-review-pool" : undefined}
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 2,
        p: 2,
        bgcolor: "background.paper",
      }}
    >
      <Stack
        direction="row"
        justifyContent="space-between"
        alignItems="flex-start"
        gap={1}
        sx={{ mb: open ? 1.5 : 0 }}
      >
        <Box
          component="button"
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls={`${poolId}-pool-body`}
          sx={{
            flex: 1,
            minWidth: 0,
            p: 0,
            border: "none",
            bgcolor: "transparent",
            textAlign: "left",
            cursor: "pointer",
            display: "flex",
            alignItems: "flex-start",
            gap: 1,
            "&:focus-visible": {
              outline: "2px solid",
              outlineColor: "primary.main",
              outlineOffset: 2,
              borderRadius: 1,
            },
          }}
        >
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography id={`${poolId}-pool-title`} variant="subtitle1" sx={{ fontWeight: 700 }}>
              {title}
              {!loading ? (
                <Typography component="span" variant="subtitle1" color="text.secondary" sx={{ fontWeight: 500 }}>
                  {` (${rules.length})`}
                </Typography>
              ) : null}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25 }}>
              {helper}
            </Typography>
          </Box>
          <Box
            aria-hidden
            sx={{
              mt: 0.25,
              display: "inline-flex",
              color: "text.secondary",
              transform: open ? "rotate(180deg)" : "rotate(0deg)",
              transition: "transform 160ms ease",
            }}
          >
            <ExpandMoreRoundedIcon fontSize="small" />
          </Box>
        </Box>
        {open && showApproveAll && filteredRules.length > 0 && onApproveAll ? (
          <Tooltip title="Approve every rule in this pool after you have read them.">
            <span>
              <Button
                variant="outlined"
                size="small"
                disabled={busy === "all"}
                onClick={onApproveAll}
                aria-label="Approve all rules in awaiting review pool"
              >
                Approve all
              </Button>
            </span>
          </Tooltip>
        ) : null}
      </Stack>

      <Collapse in={open} timeout="auto">
        <Box id={`${poolId}-pool-body`}>
          <FilterBar
            search={search}
            onSearchChange={setSearch}
            searchPlaceholder="Search by guideline, recommendation, or rule name"
            aria-label={`Search ${title.toLowerCase()}`}
            trailing={
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                <FormControl size="small" sx={{ minWidth: 130 }}>
                  <InputLabel id={`${poolId}-page-size-label`}>Per page</InputLabel>
                  <Select
                    labelId={`${poolId}-page-size-label`}
                    value={pageSize}
                    label="Per page"
                    onChange={(e) => setPageSize(Number(e.target.value))}
                  >
                    <MenuItem value={10}>10</MenuItem>
                    <MenuItem value={20}>20</MenuItem>
                    <MenuItem value={50}>50</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
            }
          />

          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 1.5, mb: 1.5 }}>
            <Autocomplete
              size="small"
              options={[ALL, ...guidelineOptions]}
              value={guidelineFilter}
              onChange={(_, value) => setGuidelineFilter(value ?? ALL)}
              getOptionLabel={(opt) => (opt === ALL ? "All guidelines" : opt)}
              sx={{ minWidth: 180, flex: 1 }}
              renderInput={(params) => (
                <TextField {...params} label="Guideline" inputProps={{ ...params.inputProps, "aria-label": `${title} guideline filter` }} />
              )}
            />
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel id={`${poolId}-strength-label`}>Action type</InputLabel>
              <Select
                labelId={`${poolId}-strength-label`}
                value={strengthFilter}
                label="Action type"
                onChange={(e) => setStrengthFilter(e.target.value)}
              >
                <MenuItem value={ALL}>All action types</MenuItem>
                {strengthOptions.map((value) => (
                  <MenuItem key={value} value={value}>
                    {strengthLabel(value)}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Stack>

          {loading ? (
            <SkeletonList rows={3} itemHeight={72} data-testid={`${poolId}-pool-skeleton`} />
          ) : filteredRules.length === 0 ? (
            <Box data-tour={poolId === "pending" ? "cg-05-card" : undefined}>
              <EmptyState icon={<HistoryOutlinedIcon fontSize="large" />} title={emptyTitle} body={emptyBody} />
            </Box>
          ) : (
            <>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  Showing {pagination.from}-{pagination.to} of {pagination.total}
                  {rules.length >= loadCap ? ` (first ${loadCap} loaded -- narrow with search)` : ""}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Click a row to expand
                </Typography>
              </Stack>
              <Stack spacing={0}>
                {pagination.pageRules.map((rule, index) => (
                  <RuleAccordionCard
                    key={rule.rule_id}
                    rule={rule}
                    expanded={!!expandedRules[rule.rule_id]}
                    busy={busy}
                    index={index}
                    statusFilter={statusFilter}
                    onToggle={() => onToggle(rule.rule_id)}
                    onEdit={() => onEdit(rule)}
                    onApprove={onApprove ? () => onApprove(rule) : undefined}
                    onReject={onReject ? () => onReject(rule) : undefined}
                  />
                ))}
              </Stack>
              {pagination.totalPages > 1 ? (
                <Box sx={{ display: "flex", justifyContent: "center", mt: 2 }}>
                  <Pagination
                    count={pagination.totalPages}
                    page={pagination.page}
                    onChange={(_, next) => setPage(next)}
                    color="primary"
                    size="small"
                    aria-label={`${title} pagination`}
                  />
                </Box>
              ) : null}
            </>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}
