"use client";

// -- PathwayToolbar.tsx --------------------------------------------------------
// Top chrome for the pathway editor.
//
// Owns: visual layout of the back arrow, pathway name input, lifecycle status
// chip, save / publish / retire actions, "Add data source", "Add output",
// "Add a step", auto-layout, test run, run all, batch dry run, version
// history, and delete buttons.
//
// Stateless: every piece of state and every handler is supplied by the parent
// page so we can decompose the orchestrator without changing behaviour.

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CloseIcon from "@mui/icons-material/Close";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import HistoryIcon from "@mui/icons-material/History";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import SaveIcon from "@mui/icons-material/Save";

import {
  SOURCE_DEFINITIONS,
  type SourceType,
} from "@/components/pathway/nodes/SourceNode";
import {
  OUTPUT_DEFINITIONS,
  type OutputType,
} from "@/components/pathway/nodes/OutputNode";
import { SUBGRAPH_OPTIONS } from "@/components/pathway/config/subgraphs";

import {
  formatSaveTime,
  lifecycleColor,
  lifecycleLabel,
  type PlanLifecycleStatus,
} from "./utils";

export interface PathwayToolbarProps {
  planName: string;
  onPlanNameChange: (name: string) => void;
  planStatus: PlanLifecycleStatus;
  isSaving: boolean;
  isDeletingPathway: boolean;
  isTestRunning: boolean;
  isBatchRunning: boolean;
  isNew: boolean;
  isSeededPathway: boolean;
  hasTestTrace: boolean;
  hasTestInput: boolean;
  executionNodeCount: number;
  lastSaved: Date | null;
  saveError: string | null;
  onClearSaveError: () => void;
  onBack: () => void;
  onSaveDraft: () => void;
  onPublish: () => void;
  onRetire: () => void;
  onAddSourceNode: (type: SourceType) => void;
  onAddOutputNode: (type: OutputType) => void;
  onAddViewerNode: () => void;
  onAddAction: (subgraphId: string) => void;
  onAutoLayout: () => void;
  onClearTestTrace: () => void;
  onOpenTestRun: () => void;
  onRunAllSteps: () => void;
  onOpenBatchPanel: () => void;
  onOpenHistory: () => void;
  onOpenDelete: () => void;
}

export function PathwayToolbar(props: PathwayToolbarProps) {
  const {
    planName,
    onPlanNameChange,
    planStatus,
    isSaving,
    isDeletingPathway,
    isTestRunning,
    isBatchRunning,
    isNew,
    isSeededPathway,
    hasTestTrace,
    hasTestInput,
    executionNodeCount,
    lastSaved,
    saveError,
    onClearSaveError,
    onBack,
    onSaveDraft,
    onPublish,
    onRetire,
    onAddSourceNode,
    onAddOutputNode,
    onAddViewerNode,
    onAddAction,
    onAutoLayout,
    onClearTestTrace,
    onOpenTestRun,
    onRunAllSteps,
    onOpenBatchPanel,
    onOpenHistory,
    onOpenDelete,
  } = props;

  return (
    <Box
      data-testid="pathway-toolbar"
      sx={{
        px: 2,
        py: 1.25,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: 1,
        borderColor: "divider",
        overflowX: "auto",
        flexShrink: 0,
      }}
    >
      <IconButton
        size="small"
        onClick={onBack}
        sx={{ flexShrink: 0 }}
        aria-label="Back to pathway list"
      >
        <ArrowBackIcon />
      </IconButton>
      <TextField
        size="small"
        placeholder="Pathway name"
        value={planName}
        onChange={(e) => onPlanNameChange(e.target.value)}
        sx={{ width: 200, flexShrink: 0 }}
        inputProps={{ "aria-label": "Pathway name" }}
      />
      <Chip
        size="small"
        label={lifecycleLabel(planStatus)}
        color={lifecycleColor(planStatus)}
        variant="outlined"
        sx={{ fontWeight: 600, fontSize: "0.72rem", flexShrink: 0 }}
      />
      {planStatus !== "retired" ? (
        <Tooltip title="Mark this pathway as retired (no longer in use)">
          <Button
            size="small"
            variant="text"
            color="inherit"
            sx={{
              textTransform: "none",
              fontSize: "0.72rem",
              color: "text.disabled",
              minWidth: 0,
              px: 1,
              flexShrink: 0,
            }}
            onClick={onRetire}
          >
            Retire
          </Button>
        </Tooltip>
      ) : null}
      <Box sx={{ flex: 1, minWidth: 8 }} />
      <Button
        variant="outlined"
        size="small"
        startIcon={
          isSaving ? (
            <CircularProgress size={13} color="inherit" />
          ) : (
            <SaveIcon />
          )
        }
        disabled={isSaving}
        onClick={onSaveDraft}
        sx={{ textTransform: "none", minWidth: 100, flexShrink: 0 }}
      >
        {isSaving ? "Saving..." : "Save draft"}
      </Button>
      <Tooltip
        title={
          planStatus === "active"
            ? "Re-publish to apply latest draft changes to live"
            : "Validate and publish this pathway to live"
        }
      >
        <span style={{ flexShrink: 0 }}>
          <Button
            variant="contained"
            size="small"
            color="success"
            startIcon={<CloudUploadIcon />}
            disabled={isSaving}
            onClick={onPublish}
            sx={{ textTransform: "none", minWidth: 90 }}
          >
            Publish
          </Button>
        </span>
      </Tooltip>
      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
      {!isSaving && lastSaved ? (
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{
            fontSize: "0.7rem",
            flexShrink: 0,
            whiteSpace: "nowrap",
          }}
        >
          Saved {formatSaveTime(lastSaved)}
        </Typography>
      ) : null}
      {saveError ? (
        <Alert
          severity="error"
          sx={{ py: 0, fontSize: "0.72rem", flexShrink: 0 }}
          onClose={onClearSaveError}
        >
          {saveError}
        </Alert>
      ) : null}
      <FormControl size="small" sx={{ minWidth: 160, flexShrink: 0 }}>
        <InputLabel>Add a data source</InputLabel>
        <Select
          label="Add a data source"
          value=""
          onChange={(e) => {
            if (e.target.value) onAddSourceNode(e.target.value as SourceType);
          }}
        >
          <MenuItem value="">Add a data source...</MenuItem>
          {(
            Object.entries(SOURCE_DEFINITIONS) as [
              SourceType,
              (typeof SOURCE_DEFINITIONS)[SourceType],
            ][]
          ).map(([type, meta]) => (
            <MenuItem key={type} value={type}>
              <Box>
                <Typography variant="body2">{meta.label}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {meta.description}
                </Typography>
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 160, flexShrink: 0 }}>
        <InputLabel>Add an output</InputLabel>
        <Select
          label="Add an output"
          value=""
          onChange={(e) => {
            const val = e.target.value;
            if (!val) return;
            if (val === "__viewer__") {
              onAddViewerNode();
              return;
            }
            onAddOutputNode(val as OutputType);
          }}
        >
          <MenuItem value="">Add an output...</MenuItem>
          {(
            Object.entries(OUTPUT_DEFINITIONS) as [
              OutputType,
              (typeof OUTPUT_DEFINITIONS)[OutputType],
            ][]
          ).map(([type, meta]) => (
            <MenuItem key={type} value={type}>
              <Box>
                <Typography variant="body2">{meta.label}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {meta.description}
                </Typography>
              </Box>
            </MenuItem>
          ))}
          <Divider />
          <MenuItem value="__viewer__">
            <Box>
              <Typography variant="body2">Mini HITL viewer</Typography>
              <Typography variant="caption" color="text.secondary">
                Canvas-only preview node - inspect step output in context
              </Typography>
            </Box>
          </MenuItem>
        </Select>
      </FormControl>

      <FormControl size="small" sx={{ minWidth: 170, flexShrink: 0 }}>
        <InputLabel>Add a step</InputLabel>
        <Select
          label="Add a step"
          value=""
          onChange={(e) => onAddAction(e.target.value)}
        >
          <MenuItem value="">Add a step...</MenuItem>
          <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>
            Clinical Steps
          </MenuItem>
          {SUBGRAPH_OPTIONS.map((s) => (
            <MenuItem key={s.id} value={s.id}>
              {s.label}
            </MenuItem>
          ))}
          <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>
            Flow Control
          </MenuItem>
          <MenuItem value="condition">Condition</MenuItem>
          <MenuItem value="parallel">Parallel</MenuItem>
          <MenuItem value="merge">Merge</MenuItem>
          <MenuItem value="transform">Transform</MenuItem>
          <MenuItem value="trigger">Trigger</MenuItem>
          <MenuItem disabled sx={{ fontWeight: 700, opacity: 1 }}>
            Connectors
          </MenuItem>
          <MenuItem value="rest_connector">REST API Call</MenuItem>
          <MenuItem value="queue_publish">Queue Publish</MenuItem>
        </Select>
      </FormControl>
      <Tooltip title="Auto-layout - rearrange steps into a tidy flow (top to bottom)">
        <IconButton
          size="small"
          onClick={onAutoLayout}
          sx={{
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1.5,
            flexShrink: 0,
          }}
          aria-label="Auto-layout pathway"
        >
          <AccountTreeIcon sx={{ fontSize: "1.1rem" }} />
        </IconButton>
      </Tooltip>
      {hasTestTrace ? (
        <Tooltip title="Clear test results">
          <IconButton
            size="small"
            onClick={onClearTestTrace}
            sx={{
              border: "1px solid",
              borderColor: "success.light",
              borderRadius: 1.5,
              color: "success.main",
              flexShrink: 0,
            }}
            aria-label="Clear test results"
          >
            <CloseIcon sx={{ fontSize: "1rem" }} />
          </IconButton>
        </Tooltip>
      ) : null}
      <Tooltip title="Dry-run the pipeline with sample data - opens the input dialog">
        <span style={{ flexShrink: 0 }}>
          <Button
            size="small"
            variant="outlined"
            color="success"
            startIcon={
              isTestRunning ? (
                <CircularProgress size={13} color="inherit" />
              ) : (
                <PlayArrowIcon />
              )
            }
            disabled={isTestRunning || executionNodeCount === 0}
            onClick={onOpenTestRun}
            sx={{ textTransform: "none", minWidth: 85 }}
          >
            {isTestRunning ? "Running..." : "Test run"}
          </Button>
        </span>
      </Tooltip>
      <Tooltip
        title={
          hasTestInput
            ? "Re-run every step with the same test input - stops at the first failure"
            : "Run all steps - opens the input dialog (no previous run yet)"
        }
      >
        <span style={{ flexShrink: 0 }}>
          <Button
            size="small"
            variant={hasTestInput ? "contained" : "outlined"}
            color="success"
            startIcon={
              isTestRunning ? (
                <CircularProgress size={13} color="inherit" />
              ) : (
                <PlayArrowIcon />
              )
            }
            disabled={isTestRunning || executionNodeCount === 0}
            onClick={onRunAllSteps}
            sx={{ textTransform: "none", minWidth: 100 }}
          >
            {isTestRunning ? "Running..." : "Run all steps"}
          </Button>
        </span>
      </Tooltip>
      <Tooltip title="Batch dry-run - run the draft pathway against real Training Candidates from the Knowledge Graph">
        <span style={{ flexShrink: 0 }}>
          <Button
            size="small"
            variant="outlined"
            color="secondary"
            startIcon={
              isBatchRunning ? (
                <CircularProgress size={13} color="inherit" />
              ) : (
                <PlayArrowIcon />
              )
            }
            disabled={
              isBatchRunning || isTestRunning || executionNodeCount === 0
            }
            onClick={onOpenBatchPanel}
            sx={{ textTransform: "none", minWidth: 100 }}
          >
            {isBatchRunning ? "Running..." : "Batch dry run"}
          </Button>
        </span>
      </Tooltip>
      {!isNew ? (
        <Tooltip title="Version history - view and restore previous published versions">
          <IconButton
            size="small"
            onClick={onOpenHistory}
            sx={{
              border: "1px solid",
              borderColor: "divider",
              borderRadius: 1.5,
              flexShrink: 0,
            }}
            aria-label="Open version history"
          >
            <HistoryIcon sx={{ fontSize: "1.1rem" }} />
          </IconButton>
        </Tooltip>
      ) : null}
      {!isNew ? (
        <Tooltip
          title={
            isSeededPathway
              ? "Seeded pathways cannot be deleted from the UI"
              : "Delete this pathway permanently"
          }
        >
          <span style={{ flexShrink: 0 }}>
            <Button
              variant="outlined"
              size="small"
              color="error"
              startIcon={<DeleteOutlineIcon />}
              disabled={isSaving || isDeletingPathway || isSeededPathway}
              onClick={onOpenDelete}
              sx={{ textTransform: "none", minWidth: 90 }}
            >
              Delete
            </Button>
          </span>
        </Tooltip>
      ) : null}
    </Box>
  );
}
