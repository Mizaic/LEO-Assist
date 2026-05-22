/**
 * Plain-English authoring canvas for the EditRuleDialog (Phase 3).
 *
 * Replaces the visible operator tree as the primary editing surface.
 * The canvas is a top-down stack of "sentence cards":
 *
 *   1. WhoCard    -- "Patient must have ..." rows for demographic /
 *                    concept / AT_LEAST conditions that apply across
 *                    every pathway.
 *   2. PathwayCards -- one card per OR branch with optional plain-
 *                      English name; the first card title is "Pathway
 *                      A" (or its name) so reviewers can see at a
 *                      glance how many alternatives exist.
 *   3. NoneOfCard -- optional "Patient must NOT have any of these"
 *                    block.
 *
 * Anything outside the recognised shapes shows an "Open Advanced view
 * to edit this rule" prompt and renders the operator tree elsewhere
 * on the page (Step1Who handles the demote-to-Accordion). The canvas
 * never silently hides information.
 *
 * Rendering is delegated to ``SentenceRow`` per row; tree-mutation
 * callbacks (``onSelectNode``, ``onRequestAdd``, ``onUpdate``,
 * ``onRequestCoach``) are passed straight through and reuse the
 * existing dialog plumbing -- the canvas does NOT introduce a new
 * mutation API. That keeps the saved tree shape unchanged and lets
 * the backend roundtrip the same JSON it always has.
 *
 * Atlas trace:
 *   UN: UN-26E57FA1
 *   DI: DI-C46DDFA3 (Phase 3 sentence canvas)
 *   DO: DO-D4D4CAA8 (Phase 3 implementation)
 *   Risk: R-5F11517C (Phase 3 unsupported-shape masking)
 *   VT: VT-123BDE46 (Phase 3 verification)
 *
 * Phase 4 trace (inline sandbox impact badges):
 *   DI: DI-D801A490
 *   DO: DO-0D8619CE
 *   Risk: R-8B052FB8
 *   VT: VT-B668D256
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import SentenceRow from "./SentenceRow";
import {
  ADD_BAR_LABELS,
  CANVAS_CARDS,
  PATHWAY_NAME,
  SANDBOX_BADGE,
} from "./copy";
import {
  treeToCanvas,
  type CanvasModel,
  type PathwayCard as PathwayCardModel,
} from "./treeToCanvas";
import type { EditableLogicNode, NodeUpdate } from "./types";

/**
 * Phase 4 -- per-card sandbox impact badge.
 *
 * The TestPatientsPanel computes a single fire/no-fire summary for
 * the whole rule; we surface it next to every top-level sentence
 * card on the canvas so the reviewer sees the answer no matter
 * which card they are working on. The badge advertises freshness so
 * reviewers know whether the count reflects the current draft or an
 * older version.
 */
export interface SandboxImpactBadge {
  status: "fresh" | "stale" | "running" | "empty";
  firingPatients: number;
  totalPatients: number;
}

interface Props {
  tree: EditableLogicNode;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (
    parentNodeId: string,
    anchor?: HTMLElement | null,
  ) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
  /** Opens the Advanced view (LogicTreeEditor) when the canvas cannot
   *  edit the current shape. Owned by Step1Who. */
  onOpenAdvancedView?: () => void;
  /** Phase 4 -- latest sandbox replay summary, surfaced inline on
   *  each top-level card so the reviewer sees impact next to the
   *  sentences. Omitted when the panel has not yet provided one. */
  sandboxBadge?: SandboxImpactBadge;
}

const CANVAS_PATHWAY_ACCENTS = [
  { stripe: "primary.main", chipBg: "primary.50", chipFg: "primary.dark" },
  { stripe: "info.main", chipBg: "info.50", chipFg: "info.dark" },
  { stripe: "secondary.main", chipBg: "secondary.50", chipFg: "secondary.dark" },
  { stripe: "success.main", chipBg: "success.50", chipFg: "success.dark" },
] as const;

function pathwayAccent(index: number) {
  return CANVAS_PATHWAY_ACCENTS[index % CANVAS_PATHWAY_ACCENTS.length];
}

export default function SentenceCanvas(props: Props) {
  const model: CanvasModel = treeToCanvas(props.tree);

  if (model.kind === "unsupported") {
    return (
      <UnsupportedShapePrompt
        reason={model.reason}
        onOpenAdvancedView={props.onOpenAdvancedView}
      />
    );
  }

  return (
    <Stack spacing={2} role="region" aria-label="Sentence canvas">
      {model.whoCard && (
        <WhoCardView
          card={model.whoCard}
          showAlternativesButton={!model.pathwayParentNodeId}
          {...props}
        />
      )}
      {model.pathwayParentNodeId && model.pathways && (
        <PathwaysSection
          parentNodeId={model.pathwayParentNodeId}
          cards={model.pathways}
          {...props}
        />
      )}
      {model.noneOf && (
        <NoneOfCardView card={model.noneOf} {...props} />
      )}
      {!model.whoCard && !model.pathways && !model.noneOf && (
        <EmptyCanvas
          parentNodeId={model.rootNodeId}
          onRequestAdd={props.onRequestAdd}
        />
      )}
    </Stack>
  );
}

/**
 * Inline pill that surfaces the sandbox replay impact next to a
 * card title. The text is kept short so it fits in the card chrome
 * without wrapping; the aria-label is the longer human-readable
 * sentence so screen-reader users get the full context.
 */
function ImpactBadge({
  badge,
}: {
  badge: SandboxImpactBadge | undefined;
}) {
  if (!badge) return null;
  if (badge.status === "running") {
    return (
      <Chip
        size="small"
        variant="outlined"
        color="info"
        label={SANDBOX_BADGE.runningLabel}
        aria-label={SANDBOX_BADGE.ariaLabel}
        sx={{ height: 22, fontSize: "0.7rem", fontWeight: 600 }}
      />
    );
  }
  if (badge.status === "empty") {
    return (
      <Chip
        size="small"
        variant="outlined"
        label={SANDBOX_BADGE.emptyLabel}
        aria-label={SANDBOX_BADGE.ariaLabel}
        sx={{
          height: 22,
          fontSize: "0.7rem",
          fontWeight: 600,
          color: "text.secondary",
          borderColor: "divider",
        }}
      />
    );
  }
  const fresh = SANDBOX_BADGE.freshLabel(
    badge.firingPatients,
    badge.totalPatients,
  );
  const isAllFiring =
    badge.totalPatients > 0 && badge.firingPatients === badge.totalPatients;
  const isNoneFiring = badge.firingPatients === 0 && badge.totalPatients > 0;
  if (badge.status === "stale") {
    return (
      <Chip
        size="small"
        variant="outlined"
        color="warning"
        label={`${fresh} (stale)`}
        aria-label={`${fresh}. ${SANDBOX_BADGE.staleLabel}`}
        sx={{ height: 22, fontSize: "0.7rem", fontWeight: 600 }}
      />
    );
  }
  return (
    <Chip
      size="small"
      variant="outlined"
      color={isNoneFiring ? "default" : isAllFiring ? "success" : "primary"}
      label={fresh}
      aria-label={fresh}
      sx={{ height: 22, fontSize: "0.7rem", fontWeight: 600 }}
    />
  );
}

interface CardShellProps {
  title: string;
  subtitle?: string;
  ariaLabel?: string;
  children: React.ReactNode;
  accent?: "default" | "warning";
  /** Optional impact badge rendered to the right of the card title. */
  rightAdornment?: React.ReactNode;
}

function CardShell({
  title,
  subtitle,
  ariaLabel,
  children,
  accent = "default",
  rightAdornment,
}: CardShellProps) {
  const borderColor = accent === "warning" ? "warning.200" : "divider";
  const stripeColor = accent === "warning" ? "warning.main" : "primary.main";
  return (
    <Box
      role="region"
      aria-label={ariaLabel ?? title}
      sx={{
        borderRadius: 2,
        border: "1px solid",
        borderColor,
        bgcolor: "background.paper",
        overflow: "hidden",
        boxShadow:
          "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04)",
      }}
    >
      <Box aria-hidden sx={{ height: 4, width: "100%", bgcolor: stripeColor }} />
      <Box sx={{ p: 1.75 }}>
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          sx={{ flexWrap: "wrap", rowGap: 0.5 }}
        >
          <Typography
            variant="subtitle2"
            sx={{
              fontWeight: 700,
              lineHeight: 1.3,
              flex: 1,
              color: accent === "warning" ? "warning.dark" : "text.primary",
            }}
          >
            {title}
          </Typography>
          {rightAdornment}
        </Stack>
        {subtitle && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 0.25, lineHeight: 1.4 }}
          >
            {subtitle}
          </Typography>
        )}
        <Box sx={{ mt: 1.25 }}>{children}</Box>
      </Box>
    </Box>
  );
}

interface WhoCardViewProps extends Props {
  card: import("./treeToCanvas").WhoCard;
  showAlternativesButton?: boolean;
}

function WhoCardView({
  card,
  showAlternativesButton = false,
  selectedNodeId,
  onSelectNode,
  onRequestAdd,
  onRequestCoach,
  onUpdate,
  sandboxBadge,
}: WhoCardViewProps) {
  return (
    <CardShell
      title={CANVAS_CARDS.whoTitle}
      rightAdornment={<ImpactBadge badge={sandboxBadge} />}
    >
      {card.rows.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ fontStyle: "italic", mb: 1 }}
        >
          {CANVAS_CARDS.whoEmpty}
        </Typography>
      ) : (
        <Stack spacing={0.75} divider={<RowDivider />}>
          {card.rows.map((row) => (
            <SentenceRow
              key={row.nodeId}
              row={row}
              selectedNodeId={selectedNodeId}
              onSelectConcept={onSelectNode}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
              onUpdate={onUpdate}
            />
          ))}
        </Stack>
      )}
      <CanvasAddBar
        parentNodeId={card.parentNodeId}
        onRequestAdd={onRequestAdd}
        onUpdate={onUpdate}
        showAlternativesButton={showAlternativesButton}
      />
    </CardShell>
  );
}

interface PathwaysSectionProps extends Props {
  parentNodeId: string;
  cards: PathwayCardModel[];
}

function PathwaysSection({
  parentNodeId,
  cards,
  selectedNodeId,
  onSelectNode,
  onRequestAdd,
  onRequestCoach,
  onUpdate,
  sandboxBadge,
}: PathwaysSectionProps) {
  return (
    <Box role="region" aria-label={CANVAS_CARDS.pathwaysTitle}>
      <Stack
        direction="row"
        alignItems="center"
        spacing={1}
        sx={{ mb: 1.25, flexWrap: "wrap", rowGap: 0.5 }}
      >
        <Typography
          variant="subtitle2"
          sx={{ fontWeight: 700, color: "text.primary", flex: 1 }}
        >
          {CANVAS_CARDS.pathwaysTitle}
        </Typography>
        <ImpactBadge badge={sandboxBadge} />
        <Tooltip title={ADD_BAR_LABELS.pathway}>
          <Chip
            icon={<AddIcon sx={{ fontSize: 14 }} />}
            label="Add pathway"
            size="small"
            variant="outlined"
            color="primary"
            onClick={() =>
              onUpdate({
                kind: "add_group",
                parentNodeId,
                groupKind: "AND",
              })
            }
            sx={{
              height: 24,
              fontSize: "0.72rem",
              fontWeight: 600,
              borderRadius: 1.5,
              bgcolor: "background.paper",
            }}
          />
        </Tooltip>
      </Stack>
      {cards.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ fontStyle: "italic" }}
        >
          {CANVAS_CARDS.pathwaysEmpty}
        </Typography>
      ) : (
        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={2}
          useFlexGap
          sx={{ alignItems: "stretch", flexWrap: "wrap" }}
        >
          {cards.map((card, i) => (
            <PathwayCardView
              key={card.nodeId}
              card={card}
              index={i}
              isLast={i === cards.length - 1}
              selectedNodeId={selectedNodeId}
              onSelectNode={onSelectNode}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
              onUpdate={onUpdate}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
}

interface PathwayCardViewProps {
  card: PathwayCardModel;
  index: number;
  isLast: boolean;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onRequestCoach?: (nodeId: string, anchor: HTMLElement) => void;
}

function PathwayCardView({
  card,
  index,
  isLast,
  selectedNodeId,
  onSelectNode,
  onRequestAdd,
  onRequestCoach,
  onUpdate,
}: PathwayCardViewProps) {
  const accent = pathwayAccent(index);
  const letter = String.fromCharCode(65 + index);
  const cardAriaLabel = card.name
    ? `${card.positional}: ${card.name}`
    : card.positional;
  return (
    <Box
      role="region"
      aria-label={cardAriaLabel}
      sx={{
        flex: 1,
        minWidth: { xs: "100%", md: 280 },
        position: "relative",
        borderRadius: 2,
        border: "1px solid",
        borderColor: "divider",
        bgcolor: "background.paper",
        boxShadow:
          "0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04)",
        overflow: "hidden",
      }}
    >
      <Box
        aria-hidden
        sx={{ height: 4, width: "100%", bgcolor: accent.stripe }}
      />
      <Box sx={{ p: 1.5 }}>
        <Stack
          direction="row"
          alignItems="flex-start"
          spacing={0.75}
          sx={{ mb: 1 }}
        >
          <Box
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.5,
              px: 0.85,
              py: 0.25,
              borderRadius: 1,
              bgcolor: accent.chipBg,
              color: accent.chipFg,
              fontSize: "0.7rem",
              fontWeight: 700,
              letterSpacing: 0.4,
              textTransform: "uppercase",
              flexShrink: 0,
              mt: 0.4,
            }}
          >
            {letter}
          </Box>
          <PathwayNameField
            card={card}
            onUpdate={onUpdate}
          />
          <Tooltip title="Remove this pathway">
            <IconButton
              size="small"
              aria-label={`Remove ${card.positional}`}
              onClick={() =>
                onUpdate({ kind: "remove", nodeId: card.nodeId })
              }
              sx={{
                color: "text.secondary",
                mt: 0.2,
                "&:hover": { color: "error.main" },
              }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Stack>
        {card.rows.length === 0 ? (
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ fontStyle: "italic", mb: 0.75 }}
          >
            This pathway is empty. Add a symptom or sub-group below.
          </Typography>
        ) : (
          <Stack spacing={0.5} divider={<RowDivider />}>
            {card.rows.map((row) => (
              <SentenceRow
                key={row.nodeId}
                row={row}
                selectedNodeId={selectedNodeId}
                onSelectConcept={onSelectNode}
                onRequestAdd={onRequestAdd}
                onRequestCoach={onRequestCoach}
                onUpdate={onUpdate}
              />
            ))}
          </Stack>
        )}
        {card.hasAndWrapper && (
          <CanvasAddBar
            parentNodeId={card.bodyParentNodeId}
            onRequestAdd={onRequestAdd}
            onUpdate={onUpdate}
            compact
          />
        )}
      </Box>
      {!isLast && (
        <Box
          aria-hidden
          sx={{
            display: { xs: "none", md: "flex" },
            position: "absolute",
            right: -14,
            top: "50%",
            transform: "translateY(-50%)",
            width: 28,
            height: 28,
            borderRadius: "50%",
            bgcolor: "background.paper",
            color: "primary.dark",
            border: "1px solid",
            borderColor: "primary.light",
            fontSize: "0.62rem",
            fontWeight: 800,
            letterSpacing: 0.5,
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1,
          }}
        >
          OR
        </Box>
      )}
    </Box>
  );
}

interface NoneOfViewProps extends Props {
  card: import("./treeToCanvas").NoneOfCard;
}

function NoneOfCardView({
  card,
  selectedNodeId,
  onSelectNode,
  onRequestAdd,
  onRequestCoach,
  onUpdate,
  sandboxBadge,
}: NoneOfViewProps) {
  return (
    <CardShell
      title={CANVAS_CARDS.noneOfTitle}
      accent="warning"
      ariaLabel={CANVAS_CARDS.noneOfTitle}
      rightAdornment={<ImpactBadge badge={sandboxBadge} />}
    >
      {card.rows.length === 0 ? (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ fontStyle: "italic", mb: 1 }}
        >
          {CANVAS_CARDS.noneOfEmpty}
        </Typography>
      ) : (
        <Stack spacing={0.5} divider={<RowDivider />}>
          {card.rows.map((row) => (
            <SentenceRow
              key={row.nodeId}
              row={row}
              selectedNodeId={selectedNodeId}
              onSelectConcept={onSelectNode}
              onRequestAdd={onRequestAdd}
              onRequestCoach={onRequestCoach}
              onUpdate={onUpdate}
            />
          ))}
        </Stack>
      )}
      <Stack direction="row" spacing={0.75} sx={{ mt: 1 }}>
        <Chip
          icon={<AddIcon sx={{ fontSize: 14 }} />}
          label={ADD_BAR_LABELS.symptom}
          size="small"
          variant="outlined"
          onClick={(e) => onRequestAdd(card.bodyParentNodeId, e.currentTarget)}
          sx={{ height: 26, fontSize: "0.72rem", fontWeight: 600 }}
        />
      </Stack>
    </CardShell>
  );
}

interface CanvasAddBarProps {
  parentNodeId: string;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
  onUpdate: (update: NodeUpdate) => void;
  compact?: boolean;
  /** When true, show a chip that inserts an OR group for alternative pathways. */
  showAlternativesButton?: boolean;
}

function CanvasAddBar({
  parentNodeId,
  onRequestAdd,
  onUpdate,
  compact,
  showAlternativesButton = false,
}: CanvasAddBarProps) {
  const addChipSx = {
    height: 26,
    fontSize: "0.72rem",
    fontWeight: 600,
    borderRadius: 1.5,
    color: "text.secondary",
    borderColor: "divider",
    bgcolor: "background.paper",
    "&:hover": {
      bgcolor: "primary.50",
      borderColor: "primary.light",
      color: "primary.dark",
    },
    "& .MuiChip-icon": { color: "inherit" },
  } as const;
  return (
    <Stack
      direction="row"
      spacing={0.75}
      alignItems="center"
      sx={{
        mt: compact ? 0.75 : 1.25,
        flexWrap: "wrap",
        rowGap: 0.5,
      }}
    >
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.symptom}
        size="small"
        variant="outlined"
        onClick={(e) => onRequestAdd(parentNodeId, e.currentTarget)}
        sx={addChipSx}
      />
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.detail}
        size="small"
        variant="outlined"
        onClick={() =>
          onUpdate({ kind: "add_demographic", parentNodeId })
        }
        sx={addChipSx}
      />
      <Chip
        icon={<AddIcon sx={{ fontSize: 14 }} />}
        label={ADD_BAR_LABELS.observation}
        size="small"
        variant="outlined"
        onClick={() =>
          onUpdate({ kind: "add_observation", parentNodeId })
        }
        sx={addChipSx}
      />
      {showAlternativesButton && (
        <Chip
          icon={<AddIcon sx={{ fontSize: 14 }} />}
          label={ADD_BAR_LABELS.alternatives}
          size="small"
          variant="outlined"
          color="primary"
          onClick={() =>
            onUpdate({
              kind: "add_group",
              parentNodeId,
              groupKind: "OR",
            })
          }
          sx={addChipSx}
        />
      )}
    </Stack>
  );
}

function RowDivider() {
  return (
    <Box
      role="presentation"
      sx={{ borderBottom: "1px dashed", borderColor: "divider", my: 0.25 }}
    />
  );
}

function PathwayNameField({
  card,
  onUpdate,
}: {
  card: PathwayCardModel;
  onUpdate: (u: NodeUpdate) => void;
}) {
  const [draft, setDraft] = useState(card.name ?? "");
  const inputId = `canvas-pathway-name-${card.nodeId}`;
  const commit = (next: string) => {
    const trimmed = next.trim();
    const current = (card.name ?? "").trim();
    if (trimmed === current) return;
    onUpdate({ kind: "set_name", nodeId: card.nodeId, name: trimmed });
  };
  return (
    <TextField
      id={inputId}
      size="small"
      variant="standard"
      value={draft}
      onChange={(e) =>
        setDraft(e.target.value.slice(0, PATHWAY_NAME.helperMaxChars))
      }
      onBlur={(e) => commit(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          (e.target as HTMLInputElement).blur();
        }
      }}
      placeholder={PATHWAY_NAME.inputPlaceholder}
      inputProps={{
        "aria-label": PATHWAY_NAME.inputAriaTemplate(card.positional),
        maxLength: PATHWAY_NAME.helperMaxChars,
      }}
      sx={{
        flex: 1,
        "& .MuiInput-input": {
          fontSize: "0.85rem",
          fontWeight: 600,
          py: 0.25,
        },
        "& .MuiInput-underline:before": {
          borderBottomStyle: "dashed",
          borderBottomColor: "divider",
        },
      }}
    />
  );
}

function EmptyCanvas({
  parentNodeId,
  onRequestAdd,
}: {
  parentNodeId: string;
  onRequestAdd: (parentNodeId: string, anchor?: HTMLElement | null) => void;
}) {
  return (
    <Box
      role="status"
      sx={{
        p: 3,
        borderRadius: 2,
        border: "1px dashed",
        borderColor: "divider",
        bgcolor: "grey.50",
        textAlign: "center",
      }}
    >
      <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5 }}>
        This rule is empty.
      </Typography>
      <Typography
        variant="body2"
        color="text.secondary"
        sx={{ mb: 2, lineHeight: 1.5 }}
      >
        Pick the first symptom or sign the patient must have for this
        rule to apply.
      </Typography>
      <Button
        variant="contained"
        startIcon={<AddIcon fontSize="small" />}
        onClick={(e) => onRequestAdd(parentNodeId, e.currentTarget)}
        sx={{ borderRadius: 999, textTransform: "none", fontWeight: 600 }}
      >
        Add the first symptom
      </Button>
    </Box>
  );
}

function UnsupportedShapePrompt({
  reason,
  onOpenAdvancedView,
}: {
  reason: string;
  onOpenAdvancedView?: () => void;
}) {
  return (
    <Box
      role="status"
      aria-label={CANVAS_CARDS.unsupportedTitle}
      sx={{
        p: 2.5,
        borderRadius: 2,
        border: "1px dashed",
        borderColor: "warning.200",
        bgcolor: "warning.50",
      }}
    >
      <Typography
        variant="subtitle2"
        sx={{ fontWeight: 700, color: "warning.dark", mb: 0.5 }}
      >
        {CANVAS_CARDS.unsupportedTitle}
      </Typography>
      <Typography
        variant="body2"
        color="text.primary"
        sx={{ lineHeight: 1.5, mb: 0.5 }}
      >
        {CANVAS_CARDS.unsupportedBody}
      </Typography>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 1.5 }}
      >
        {reason}
      </Typography>
      {onOpenAdvancedView && (
        <Button
          size="small"
          variant="outlined"
          color="warning"
          onClick={onOpenAdvancedView}
        >
          Open Advanced view
        </Button>
      )}
    </Box>
  );
}
