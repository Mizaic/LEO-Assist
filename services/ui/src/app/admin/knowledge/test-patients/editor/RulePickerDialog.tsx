"use client";

/**
 * RulePickerDialog -- tree-based picker for guideline rules.
 *
 * Designed to scale: 300+ guidelines x ~20 rules each is too long for a
 * flat dropdown, so the dialog presents a three-level tree
 * (Guideline -> Chapter -> Rule) the reviewer can browse. Every level
 * has a checkbox: ticking a guideline ticks every rule under it,
 * partial selections show as an indeterminate checkbox.
 *
 * Audience standard (UK reading age 11): the dialog uses plain English
 * throughout. Rule labels lead with the verbatim NICE recommendation
 * and a coloured priority chip (2WW / URGENT / ROUTINE). The raw rule
 * id is hidden behind a tooltip; reviewers never have to read it.
 *
 * The dialog is driven by props (controlled): the parent owns the set
 * of selected rule ids and receives the new selection on Apply.
 * Cancel discards changes.
 */

import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SearchIcon from "@mui/icons-material/Search";
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";

import type { GuidanceRulePickerEntry } from "../types";

interface RulePickerDialogProps {
  open: boolean;
  onClose: () => void;
  onApply: (selectedRuleIds: string[]) => void;
  selectedRuleIds: string[];
  rules: GuidanceRulePickerEntry[];
  loading?: boolean;
  error?: string | null;
}

interface ChapterNode {
  key: string;
  title: string;
  rules: GuidanceRulePickerEntry[];
}

interface GuidelineNode {
  key: string;
  title: string;
  chapters: ChapterNode[];
  ruleCount: number;
}

const CHAPTERLESS = "(no chapter)";
const GUIDELINELESS = "(no guideline)";

function buildTree(rules: GuidanceRulePickerEntry[]): GuidelineNode[] {
  const guidelineMap = new Map<
    string,
    { title: string; chapters: Map<string, ChapterNode> }
  >();
  for (const rule of rules) {
    const gKey = rule.guideline_id ?? rule.guideline_title ?? GUIDELINELESS;
    const gTitle = rule.guideline_title ?? GUIDELINELESS;
    let g = guidelineMap.get(gKey);
    if (!g) {
      g = { title: gTitle, chapters: new Map() };
      guidelineMap.set(gKey, g);
    }
    const chapterTitle = rule.chapter_title ?? CHAPTERLESS;
    let chapter = g.chapters.get(chapterTitle);
    if (!chapter) {
      chapter = { key: chapterTitle, title: chapterTitle, rules: [] };
      g.chapters.set(chapterTitle, chapter);
    }
    chapter.rules.push(rule);
  }
  const guidelines: GuidelineNode[] = [];
  for (const [key, value] of guidelineMap.entries()) {
    const chapters = Array.from(value.chapters.values()).sort((a, b) =>
      a.title.localeCompare(b.title),
    );
    let count = 0;
    for (const ch of chapters) count += ch.rules.length;
    guidelines.push({
      key,
      title: value.title,
      chapters,
      ruleCount: count,
    });
  }
  guidelines.sort((a, b) => a.title.localeCompare(b.title));
  return guidelines;
}

function ruleMatchesQuery(
  rule: GuidanceRulePickerEntry,
  needle: string,
): boolean {
  if (!needle) return true;
  const haystack = [
    rule.rule_id,
    rule.name ?? "",
    rule.display_label,
    rule.recommendation_text ?? "",
    rule.chapter_title ?? "",
    rule.guideline_id ?? "",
    rule.guideline_title ?? "",
    ...(rule.trigger_terms ?? []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

function priorityColor(
  priority: string | null,
): "error" | "warning" | "default" {
  if (!priority) return "default";
  const p = priority.toLowerCase();
  if (p === "2ww") return "error";
  if (p === "urgent") return "warning";
  return "default";
}

export default function RulePickerDialog({
  open,
  onClose,
  onApply,
  selectedRuleIds,
  rules,
  loading = false,
  error = null,
}: RulePickerDialogProps) {
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      setDraft(new Set(selectedRuleIds));
      setQuery("");
    }
  }, [open, selectedRuleIds]);

  const tree = useMemo(() => buildTree(rules), [rules]);

  const needle = query.trim().toLowerCase();
  const filteredTree = useMemo<GuidelineNode[]>(() => {
    if (!needle) return tree;
    const out: GuidelineNode[] = [];
    for (const g of tree) {
      const chapters: ChapterNode[] = [];
      for (const ch of g.chapters) {
        const matched = ch.rules.filter((r) => ruleMatchesQuery(r, needle));
        if (matched.length > 0) {
          chapters.push({ ...ch, rules: matched });
        }
      }
      if (chapters.length > 0) {
        let count = 0;
        for (const ch of chapters) count += ch.rules.length;
        out.push({ ...g, chapters, ruleCount: count });
      }
    }
    return out;
  }, [tree, needle]);

  // When searching, auto-expand every guideline + chapter that matched
  // so the reviewer sees the hits without clicking through.
  const effectiveExpanded = useMemo<Set<string>>(() => {
    if (!needle) return expanded;
    const set = new Set<string>();
    for (const g of filteredTree) {
      set.add(`g:${g.key}`);
      for (const ch of g.chapters) {
        set.add(`g:${g.key}|c:${ch.key}`);
      }
    }
    return set;
  }, [needle, filteredTree, expanded]);

  const toggleNode = (key: string) => {
    if (needle) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const expandAll = () => {
    const set = new Set<string>();
    for (const g of tree) {
      set.add(`g:${g.key}`);
      for (const ch of g.chapters) set.add(`g:${g.key}|c:${ch.key}`);
    }
    setExpanded(set);
  };

  const collapseAll = () => setExpanded(new Set());

  const toggleRule = (ruleId: string) => {
    setDraft((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  };

  const setBulk = (ruleIds: string[], shouldSelect: boolean) => {
    setDraft((prev) => {
      const next = new Set(prev);
      for (const id of ruleIds) {
        if (shouldSelect) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  };

  const chapterIds = (chapter: ChapterNode) =>
    chapter.rules.map((r) => r.rule_id);
  const guidelineIds = (guideline: GuidelineNode) => {
    const out: string[] = [];
    for (const ch of guideline.chapters) out.push(...chapterIds(ch));
    return out;
  };

  const groupState = (
    ids: string[],
  ): { selected: number; total: number } => {
    let selected = 0;
    for (const id of ids) {
      if (draft.has(id)) selected += 1;
    }
    return { selected, total: ids.length };
  };

  const handleApply = () => {
    onApply(Array.from(draft));
  };

  const totalRules = rules.length;
  const totalSelected = draft.size;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{ sx: { height: "80vh" } }}
    >
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={1}>
          <Box>Pick the rules that should fire</Box>
          <Chip
            size="small"
            label={`${totalSelected} selected`}
            color={totalSelected > 0 ? "primary" : "default"}
          />
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Browse by guideline. Tick a section to add every rule under it,
          or open the section to pick a single rule.
        </Typography>
      </DialogTitle>

      <DialogContent dividers sx={{ display: "flex", flexDirection: "column" }}>
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          sx={{ mb: 1.5 }}
        >
          <TextField
            size="small"
            fullWidth
            placeholder="Search by guideline, section, symptom or rule"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <SearchIcon
                  fontSize="small"
                  sx={{ mr: 1, color: "text.secondary" }}
                />
              ),
            }}
          />
          <IconButton
            size="small"
            onClick={expandAll}
            title="Expand all"
            disabled={!!needle}
          >
            <UnfoldMoreIcon fontSize="small" />
          </IconButton>
          <IconButton
            size="small"
            onClick={collapseAll}
            title="Collapse all"
            disabled={!!needle}
          >
            <UnfoldLessIcon fontSize="small" />
          </IconButton>
        </Stack>

        {error ? (
          <Alert severity="warning" sx={{ mb: 1.5 }}>
            {error}
          </Alert>
        ) : null}

        {loading ? (
          <Stack
            alignItems="center"
            justifyContent="center"
            sx={{ flex: 1 }}
          >
            <CircularProgress size={28} />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              Loading rules...
            </Typography>
          </Stack>
        ) : filteredTree.length === 0 ? (
          <Stack
            alignItems="center"
            justifyContent="center"
            sx={{ flex: 1, color: "text.secondary" }}
          >
            <Typography variant="body2">
              {needle
                ? "No rules match that search."
                : "No rules are loaded yet."}
            </Typography>
          </Stack>
        ) : (
          <Box
            sx={{
              flex: 1,
              overflowY: "auto",
              border: 1,
              borderColor: "divider",
              borderRadius: 1,
              p: 0.5,
            }}
            data-testid="rule-picker-tree"
          >
            {filteredTree.map((g) => {
              const gKey = `g:${g.key}`;
              const isOpen = effectiveExpanded.has(gKey);
              const ids = guidelineIds(g);
              const { selected, total } = groupState(ids);
              const allChecked = selected === total && total > 0;
              const someChecked = selected > 0 && selected < total;
              return (
                <Box key={gKey}>
                  <Stack
                    direction="row"
                    alignItems="center"
                    sx={{
                      px: 0.5,
                      py: 0.5,
                      borderRadius: 1,
                      "&:hover": { bgcolor: "action.hover" },
                      cursor: needle ? "default" : "pointer",
                    }}
                    onClick={() => toggleNode(gKey)}
                  >
                    {isOpen ? (
                      <ExpandMoreIcon fontSize="small" />
                    ) : (
                      <ChevronRightIcon fontSize="small" />
                    )}
                    <Checkbox
                      size="small"
                      checked={allChecked}
                      indeterminate={someChecked}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setBulk(ids, e.target.checked)}
                    />
                    <Typography
                      variant="body2"
                      sx={{ fontWeight: 600, flex: 1 }}
                    >
                      {g.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {selected > 0
                        ? `${selected} of ${total} rules`
                        : `${total} rules`}
                    </Typography>
                  </Stack>
                  <Collapse in={isOpen} unmountOnExit>
                    <Box sx={{ pl: 4 }}>
                      {g.chapters.map((ch) => {
                        const chKey = `${gKey}|c:${ch.key}`;
                        const chOpen = effectiveExpanded.has(chKey);
                        const chIds = chapterIds(ch);
                        const chState = groupState(chIds);
                        const chAll =
                          chState.selected === chState.total &&
                          chState.total > 0;
                        const chSome =
                          chState.selected > 0 &&
                          chState.selected < chState.total;
                        return (
                          <Box key={chKey}>
                            <Stack
                              direction="row"
                              alignItems="center"
                              sx={{
                                px: 0.5,
                                py: 0.5,
                                borderRadius: 1,
                                "&:hover": { bgcolor: "action.hover" },
                                cursor: needle ? "default" : "pointer",
                              }}
                              onClick={() => toggleNode(chKey)}
                            >
                              {chOpen ? (
                                <ExpandMoreIcon fontSize="small" />
                              ) : (
                                <ChevronRightIcon fontSize="small" />
                              )}
                              <Checkbox
                                size="small"
                                checked={chAll}
                                indeterminate={chSome}
                                onClick={(e) => e.stopPropagation()}
                                onChange={(e) =>
                                  setBulk(chIds, e.target.checked)
                                }
                              />
                              <Typography variant="body2" sx={{ flex: 1 }}>
                                {ch.title}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {chState.selected > 0
                                  ? `${chState.selected} of ${chState.total}`
                                  : `${chState.total}`}
                              </Typography>
                            </Stack>
                            <Collapse in={chOpen} unmountOnExit>
                              <Box sx={{ pl: 4 }}>
                                {ch.rules.map((rule) => {
                                  const checked = draft.has(rule.rule_id);
                                  return (
                                    <Stack
                                      key={rule.rule_id}
                                      direction="row"
                                      alignItems="flex-start"
                                      sx={{
                                        px: 0.5,
                                        py: 0.5,
                                        borderRadius: 1,
                                        "&:hover": {
                                          bgcolor: "action.hover",
                                        },
                                      }}
                                      title={rule.rule_id}
                                    >
                                      <Checkbox
                                        size="small"
                                        checked={checked}
                                        onChange={() =>
                                          toggleRule(rule.rule_id)
                                        }
                                      />
                                      <Stack
                                        spacing={0.25}
                                        sx={{ flex: 1, mt: 0.5 }}
                                      >
                                        <Typography
                                          variant="body2"
                                          sx={{ fontWeight: 500 }}
                                        >
                                          {rule.display_label}
                                        </Typography>
                                        <Stack
                                          direction="row"
                                          spacing={0.75}
                                          sx={{
                                            flexWrap: "wrap",
                                            rowGap: 0.5,
                                            alignItems: "center",
                                          }}
                                        >
                                          {rule.action_priority ? (
                                            <Chip
                                              size="small"
                                              label={rule.action_priority.toUpperCase()}
                                              color={priorityColor(
                                                rule.action_priority,
                                              )}
                                              variant="outlined"
                                            />
                                          ) : null}
                                          {rule.trigger_terms.length > 0 ? (
                                            <Typography
                                              variant="caption"
                                              color="text.secondary"
                                            >
                                              Triggers:{" "}
                                              {rule.trigger_terms.join(", ")}
                                            </Typography>
                                          ) : null}
                                        </Stack>
                                      </Stack>
                                    </Stack>
                                  );
                                })}
                              </Box>
                            </Collapse>
                          </Box>
                        );
                      })}
                    </Box>
                  </Collapse>
                </Box>
              );
            })}
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ flex: 1, pl: 2 }}
        >
          {totalRules > 0
            ? `Showing ${filteredTree.reduce(
                (acc, g) => acc + g.ruleCount,
                0,
              )} of ${totalRules} rules`
            : ""}
        </Typography>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleApply} variant="contained">
          Apply {totalSelected > 0 ? `(${totalSelected})` : ""}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
