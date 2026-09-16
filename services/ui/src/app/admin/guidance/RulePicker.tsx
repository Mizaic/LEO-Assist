/**
 * Atlas trace:
 *   DI: DI-8DD23CE2
 * Searchable, grouped checklist of active rules for pick-and-mix compile mode.
 */
"use client";

import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { ReviewListCard } from "@leo/design-system";
import type { ReviewListItem } from "@leo/design-system";
import type { ActiveRule } from "./useBitmapLifecycle";

interface RulePickerProps {
  rules: ActiveRule[];
  selected: Set<string>;
  onToggle: (ruleId: string) => void;
  onClear: () => void;
  emptyMessage?: string;
}

function groupByGuideline(
  rules: ActiveRule[],
): Map<string, ActiveRule[]> {
  const map = new Map<string, ActiveRule[]>();
  for (const rule of rules) {
    const key = rule.guideline_title || rule.guideline_id;
    const existing = map.get(key) ?? [];
    existing.push(rule);
    map.set(key, existing);
  }
  return map;
}

function matchesSearch(rule: ActiveRule, term: string): boolean {
  const lower = term.toLowerCase();
  return (
    rule.name.toLowerCase().includes(lower) ||
    rule.guideline_title.toLowerCase().includes(lower) ||
    rule.guideline_id.toLowerCase().includes(lower)
  );
}

function buildListItems(
  rules: ActiveRule[],
  selected: Set<string>,
  onToggle: (ruleId: string) => void,
): ReviewListItem[] {
  const grouped = groupByGuideline(rules);
  const items: ReviewListItem[] = [];
  for (const [guidelineTitle, groupRules] of grouped) {
    items.push({
      id: `header-${guidelineTitle}`,
      tone: "neutral",
      title: (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 }}
        >
          {guidelineTitle}
        </Typography>
      ),
    });
    for (const rule of groupRules) {
      const checked = selected.has(rule.rule_id);
      items.push({
        id: rule.rule_id,
        tone: checked ? "positive" : "neutral",
        title: (
          <Stack direction="row" spacing={1} alignItems="center">
            <Checkbox
              size="small"
              checked={checked}
              onChange={() => onToggle(rule.rule_id)}
              inputProps={{ "aria-label": `Select rule ${rule.name}` }}
              sx={{ p: 0 }}
            />
            <Typography variant="body2">{rule.name}</Typography>
            <Chip
              label={rule.strength}
              size="small"
              variant="outlined"
              sx={{ fontSize: 10 }}
            />
          </Stack>
        ),
      });
    }
  }
  return items;
}

export default function RulePicker({
  rules,
  selected,
  onToggle,
  onClear,
  emptyMessage = "No approved rules found. Approve some rules before compiling a pick-and-mix set.",
}: RulePickerProps) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const term = search.trim();
    return term ? rules.filter((r) => matchesSearch(r, term)) : rules;
  }, [rules, search]);

  const items = useMemo(
    () => buildListItems(filtered, selected, onToggle),
    [filtered, selected, onToggle],
  );

  if (!rules.length) {
    return (
      <Alert severity="info" sx={{ mt: 1 }}>
        {emptyMessage}
      </Alert>
    );
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Stack
        direction="row"
        spacing={1}
        alignItems="center"
        sx={{ mb: 1 }}
      >
        <TextField
          size="small"
          placeholder="Search rules or guidelines..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search rules"
          sx={{ flex: 1 }}
        />
        {selected.size > 0 && (
          <>
            <Chip
              label={`${selected.size} selected`}
              size="small"
              color="primary"
            />
            <Chip
              label="Clear"
              size="small"
              variant="outlined"
              onClick={onClear}
              aria-label="Clear rule selection"
            />
          </>
        )}
      </Stack>
      {filtered.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No rules match. Adjust the search.
        </Typography>
      ) : (
        <ReviewListCard items={items} />
      )}
    </Box>
  );
}
