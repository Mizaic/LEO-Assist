/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

import Box from "@mui/material/Box";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import Typography from "@mui/material/Typography";

import ConfidenceBadge from "../ConfidenceBadge";
import type { LogicCriterion } from "../types";
import type { RecommendationStructureItem } from "./pathwayTextSplit";

/**
 * Renders `recommendation_structure` as the real nested bullet list it
 * is -- the primary rendering surface once a recommendation has parsed
 * list structure (see the plan's "How structure changes the UI"
 * section). One click per row opens the existing concept-search /
 * demographic / observation flow pre-filled from that row's own text;
 * nested `<ul>` children render as indented rows automatically, with no
 * "or"-heuristic needed -- the guideline's own markup already answered
 * where the boundary is.
 *
 * Reused for both Step 2 (all top-level items, one per pathway, with
 * `pathwayLabels`) and Step 3 (a single pathway's own nested rows, no
 * labels) -- same component, same click contract, different slice of
 * the tree passed in by the caller.
 */

export interface ListRowResolution {
  criterion?: LogicCriterion | null;
  preferredTerm?: string | null;
  /** The real tree leaf's own node_id, when this row already resolves
   * to one -- lets a caller route a click to "edit this node" instead
   * of "add a new one". Optional: Step 2's own pathway-level rows have
   * no single leaf to point at. */
  nodeId?: string | null;
}

interface Props {
  /** Intro copy shown above the list (e.g. "In people aged 55 or over with:"). */
  leadText?: string | null;
  items: RecommendationStructureItem[];
  /** Letter labels aligned 1:1 with top-level `items` (Step 2 usage only). */
  pathwayLabels?: string[];
  /** Looked up per row by its own (start, end) offset identity -- undefined
   * means "not yet resolved," rendered as an empty/unchecked row. */
  getRowResolution?: (
    item: RecommendationStructureItem
  ) => ListRowResolution | undefined;
  /**
   * `anchor` is the actual DOM element the reviewer clicked -- always
   * pass it straight through to `onRequestAdd`/`onSelectNode` so the
   * resulting search popover appears next to what was clicked instead
   * of falling back to a broken default position (see ChipSearchPopover's
   * doc comment: "anchored to the chip or +Add button the reviewer
   * just clicked").
   */
  onRowClick: (item: RecommendationStructureItem, anchor: HTMLElement) => void;
  /**
   * Optional per-row slot rendered below the row's own click target (e.g.
   * Step 3's "highlight text to add more codes" affordance). Called for
   * every row, including nested children; returning null/undefined is a
   * no-op, so existing callers (Step 2) are unaffected.
   */
  renderRowExtra?: (item: RecommendationStructureItem) => React.ReactNode;
}

function rowKey(item: RecommendationStructureItem): string {
  return `${item.start}-${item.end}`;
}

function RowStatusIcon({ resolved }: { resolved: boolean }) {
  return resolved ? (
    <CheckCircleIcon fontSize="small" sx={{ color: "#16A34A", mr: 1 }} />
  ) : (
    <RadioButtonUncheckedIcon fontSize="small" sx={{ color: "#94A3B8", mr: 1 }} />
  );
}

function RowLabel({
  item,
  label,
  resolution,
}: {
  item: RecommendationStructureItem;
  label?: string;
  resolution?: ListRowResolution;
}) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Typography variant="body2" component="span">
        {label && <strong>({label})</strong>} {item.text}
      </Typography>
      {resolution?.preferredTerm && (
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block" }}
        >
          matched to: {resolution.preferredTerm}
        </Typography>
      )}
    </Box>
  );
}

function ListRow({
  item,
  label,
  depth,
  getRowResolution,
  onRowClick,
  renderRowExtra,
}: {
  item: RecommendationStructureItem;
  label?: string;
  depth: number;
  getRowResolution?: Props["getRowResolution"];
  onRowClick: Props["onRowClick"];
  renderRowExtra?: Props["renderRowExtra"];
}) {
  const resolution = getRowResolution?.(item);
  const resolved = !!(resolution?.criterion || resolution?.preferredTerm);
  const hasChildren = !!item.children && item.children.length > 0;

  return (
    // `disablePadding` + `display: block` -- a List's direct children must
    // be <li> (axe "list" rule), and a row that also owns a nested <List>
    // (<ul>) needs to stack the button above it rather than lay them out
    // side by side, which is ListItem's flex default.
    <ListItem disablePadding sx={{ display: "block" }}>
      <ListItemButton
        data-testid={`list-row-${rowKey(item)}`}
        data-resolved={resolved}
        onClick={(e) => onRowClick(item, e.currentTarget)}
        sx={{ pl: 2 + depth * 2, alignItems: "flex-start", py: 0.75 }}
      >
        <RowStatusIcon resolved={resolved} />
        <RowLabel item={item} label={label} resolution={resolution} />
        {resolution?.criterion && (
          <Box sx={{ ml: "auto", pl: 1 }}>
            <ConfidenceBadge criterion={resolution.criterion} />
          </Box>
        )}
      </ListItemButton>
      {renderRowExtra && (
        <Box sx={{ pl: 2 + depth * 2 + 4.5 / 2, pr: 1, pb: 0.5 }}>
          {renderRowExtra(item)}
        </Box>
      )}
      {hasChildren && (
        <List disablePadding>
          {item.children!.map((child) => (
            <ListRow
              key={rowKey(child)}
              item={child}
              depth={depth + 1}
              getRowResolution={getRowResolution}
              onRowClick={onRowClick}
              renderRowExtra={renderRowExtra}
            />
          ))}
        </List>
      )}
    </ListItem>
  );
}

export default function ListRecommendationView({
  leadText,
  items,
  pathwayLabels,
  getRowResolution,
  onRowClick,
  renderRowExtra,
}: Props) {
  return (
    <Box>
      {leadText && (
        <Typography variant="body2" sx={{ mb: 1, color: "text.secondary" }}>
          {leadText}
        </Typography>
      )}
      <List disablePadding>
        {items.map((item, idx) => (
          <ListRow
            key={rowKey(item)}
            item={item}
            label={pathwayLabels?.[idx]}
            depth={0}
            getRowResolution={getRowResolution}
            onRowClick={onRowClick}
            renderRowExtra={renderRowExtra}
          />
        ))}
      </List>
    </Box>
  );
}