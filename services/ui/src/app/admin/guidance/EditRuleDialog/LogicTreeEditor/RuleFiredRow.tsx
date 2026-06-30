"use client";
/**
 * Inline row for a RULE_FIRED leaf node.
 *
 * Atlas trace: DI-6AE25829 / DO-274E5A61 / VT-5FB87951
 *
 * Renders a chain icon + rule-name chip + has-fired/has-not-fired toggle.
 * The author picks the prerequisite rule from a popover that lists active
 * rules in the same guideline (excluding the rule currently being edited).
 *
 * Atlas trace: DO-274E5A61 / DI-6AE25829
 */
import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Popover from "@mui/material/Popover";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import type { EditableLogicNode, NodeUpdate } from "../types";
import type { GuidanceRulePickerEntry } from "@/app/admin/knowledge/test-patients/types";

interface Props {
  node: EditableLogicNode;
  onUpdate: (update: NodeUpdate) => void;
  guidelineId?: string;
  currentRuleId?: string;
}

export default function RuleFiredRow({
  node,
  onUpdate,
  guidelineId,
  currentRuleId,
}: Props) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const [search, setSearch] = useState("");
  const [rules, setRules] = useState<GuidanceRulePickerEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const outcome = node.outcome ?? "fired";
  const displayName = node.display_name || node.referenced_rule_id || "";

  function openPicker(anchor: HTMLElement) {
    setAnchorEl(anchor);
    setSearch("");
  }

  function closePicker() {
    setAnchorEl(null);
  }

  useEffect(() => {
    if (!anchorEl || !guidelineId) {
      setRules([]);
      return;
    }
    setLoading(true);
    const params = new URLSearchParams({ guideline_id: guidelineId });
    fetch(`/api/guidance/test-patients/rules?${params}`)
      .then((r) => r.json())
      .then((data: GuidanceRulePickerEntry[]) => {
        const stem = (id: string) => id.split(":edit:")[0];
        const currentStem = currentRuleId ? stem(currentRuleId) : "";
        setRules(
          data.filter((r) => !currentRuleId || stem(r.rule_id) !== currentStem)
        );
      })
      .catch(() => setRules([]))
      .finally(() => setLoading(false));
  }, [anchorEl, guidelineId, currentRuleId]);

  useEffect(() => {
    if (anchorEl) {
      setTimeout(() => searchRef.current?.focus(), 60);
    }
  }, [anchorEl]);

  const filtered = rules.filter((r) => {
    const q = search.toLowerCase();
    return (
      !q ||
      (r.display_label ?? "").toLowerCase().includes(q) ||
      (r.name ?? "").toLowerCase().includes(q)
    );
  });

  function pick(rule: GuidanceRulePickerEntry) {
    onUpdate({
      kind: "set_rule_fired",
      nodeId: node.node_id,
      referenced_rule_id: rule.rule_id,
      outcome,
      display_name: rule.display_label || rule.name || rule.rule_id,
    });
    closePicker();
  }

  function toggleOutcome() {
    onUpdate({
      kind: "set_rule_fired",
      nodeId: node.node_id,
      referenced_rule_id: node.referenced_rule_id ?? "",
      outcome: outcome === "fired" ? "not_fired" : "fired",
      display_name: node.display_name ?? "",
    });
  }

  const pickerOpen = Boolean(anchorEl);

  return (
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ flexWrap: "wrap", my: 0.5 }}>
      <AccountTreeOutlinedIcon
        fontSize="small"
        sx={{ color: "text.secondary", flexShrink: 0 }}
        aria-hidden
      />

      {/* Outcome toggle */}
      <Tooltip title={outcome === "fired" ? "Switch to: has NOT fired" : "Switch to: has fired"}>
        <Box
          component="button"
          onClick={toggleOutcome}
          aria-label={
            outcome === "fired"
              ? "Condition: rule has fired (click to switch)"
              : "Condition: rule has NOT fired (click to switch)"
          }
          sx={{
            border: "1px solid",
            borderColor: outcome === "fired" ? "primary.main" : "error.main",
            borderRadius: 1,
            px: 1,
            py: 0.25,
            background: "transparent",
            color: outcome === "fired" ? "primary.main" : "error.main",
            fontSize: "0.75rem",
            fontWeight: 600,
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          {outcome === "fired" ? "has fired" : "has NOT fired"}
        </Box>
      </Tooltip>

      {/* Rule name chip / picker trigger */}
      <Chip
        label={displayName || "Pick a rule\u2026"}
        size="small"
        variant={displayName ? "filled" : "outlined"}
        color={displayName ? "default" : "warning"}
        onClick={(e) => openPicker(e.currentTarget)}
        aria-label="Pick the rule to depend on"
        sx={{ maxWidth: 260, cursor: "pointer" }}
      />

      {/* Remove */}
      <Tooltip title="Remove this rule dependency">
        <IconButton
          size="small"
          aria-label="Remove this rule dependency"
          onClick={() => onUpdate({ kind: "remove", nodeId: node.node_id })}
        >
          <DeleteOutlineIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Rule picker popover */}
      <Popover
        open={pickerOpen}
        anchorEl={anchorEl}
        onClose={closePicker}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        PaperProps={{ sx: { width: 360, maxHeight: 400, display: "flex", flexDirection: "column" } }}
      >
        <Box sx={{ p: 1, borderBottom: "1px solid", borderColor: "divider" }}>
          <TextField
            inputRef={searchRef}
            size="small"
            fullWidth
            placeholder="Search rules\u2026"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            inputProps={{ "aria-label": "Search rules" }}
          />
        </Box>
        <Box sx={{ overflowY: "auto", flex: 1 }}>
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", p: 2 }}>
              <CircularProgress size={20} />
            </Box>
          ) : !guidelineId ? (
            <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
              No guideline linked to this rule yet. Save the rule to a guideline first.
            </Typography>
          ) : filtered.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ p: 1.5 }}>
              {search ? "No rules match your search." : "No other rules in this guideline."}
            </Typography>
          ) : (
            filtered.map((r) => (
              <MenuItem
                key={r.rule_id}
                onClick={() => pick(r)}
                selected={r.rule_id === node.referenced_rule_id}
                sx={{ whiteSpace: "normal", alignItems: "flex-start" }}
              >
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 500, lineHeight: 1.3 }}>
                    {r.display_label || r.name || r.rule_id}
                  </Typography>
                  {r.name && r.display_label && r.name !== r.display_label && (
                    <Typography variant="caption" color="text.secondary">
                      {r.name}
                    </Typography>
                  )}
                </Box>
              </MenuItem>
            ))
          )}
        </Box>
      </Popover>
    </Stack>
  );
}
