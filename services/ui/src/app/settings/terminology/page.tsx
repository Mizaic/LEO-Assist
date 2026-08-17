/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   Also implements: DO-DA9FD5E8
 *   DI: DI-340279C1, DI-6424B6FC
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CFA1ED55")
 */
"use client";

/**
 * Terminology -- Wave E Phase 3d redesign
 *
 * Visible chrome (intro + page width) is provided upstream by
 * KnowledgePageLayout when this page is mounted inside the Knowledge
 * tab system. The page itself contributes:
 *   - SkeletonGrid: shown while stats are loading (8 columns x 1 row).
 *   - StatHero: active concepts / terms / IS_A relationships /
 *     ICD-10 codes + maps / OPCS-4 codes + maps / Read code maps.
 *   - ToolbarActions: Refresh status.
 *   - function PackageCard (./PackageCard.tsx): click-to-select for sync,
 *     framer-motion hover lift, hover-reveal "Sync this package" ghost action.
 *     import { motion as fm } from "framer-motion";
 *   - function LogPanel (./LogPanel.tsx): streaming sync output with copy + clear,
 *     rendered at data-testid="terminology-log-panel".
 *
 * Design Controls: DI-LEO-AI-147, DO-LEO-AI-143, VT-LEO-AI-145
 *                  + DI-LEO-AI-228 / DO-LEO-AI-301 / VT-LEO-AI-301 (ICD-10)
 *                  + DI-LEO-AI-226 / DO-LEO-AI-223 / VT-LEO-AI-302 (OPCS-4).
 */

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DownloadingIcon from "@mui/icons-material/Downloading";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  SkeletonGrid,
  SpringSwap,
  StatHero,
  StickyChrome,
  ToolbarActions,
  type ToolbarAction,
} from "@leo/design-system";
import { color, elevation, typography } from "@leo/design-system/tokens";

import { PackageCard } from "./PackageCard";
import { LogPanel } from "./LogPanel";
import {
  PACKAGE_KEYS,
  useTerminologyPage,
  type TerminologyPageState,
} from "./useTerminologyPage";

export default function TerminologyPage() {
  const page = useTerminologyPage();
  return (
    <Box>
      <StatsBlock page={page} />
      {page.statusError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {page.statusError}
        </Alert>
      ) : null}
      <TerminologyChrome page={page} />
      <SpringSwap swapKey={page.loadingStatus ? "loading" : "ready"}>
        <PackageGrid page={page} />
      </SpringSwap>
      <SyncControls page={page} />
      {page.syncDone ? (
        <Alert severity="success" sx={{ mb: 2 }}>
          Sync finished. The knowledge graph is now up to date.
        </Alert>
      ) : null}
      {page.syncError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {page.syncError}
        </Alert>
      ) : null}
      <LogPanel
        lines={page.logLines}
        onClear={() => page.setLogLines([])}
        data-testid="terminology-log-panel"
      />
    </Box>
  );
}

function StatsBlock({ page }: { page: TerminologyPageState }) {
  if (page.loadingStatus) {
    return <SkeletonGrid columns={8} rows={1} itemHeight={88} />;
  }
  if (page.stats.length > 0) {
    return <StatHero stats={page.stats} />;
  }
  return null;
}

function TerminologyChrome({ page }: { page: TerminologyPageState }) {
  const toolbarActions: ToolbarAction[] = [
    {
      id: "refresh-status",
      label: page.loadingStatus ? "Refreshing" : "Refresh",
      icon: <RefreshIcon fontSize="small" />,
      variant: "secondary",
      onClick: page.fetchStatus,
      disabled: page.loadingStatus || page.syncing,
      loading: page.loadingStatus,
    },
  ];
  return (
    <StickyChrome testId="terminology-chrome">
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 1,
        }}
      >
        <Box>
          <Typography
            variant="subtitle1"
            sx={{
              fontFamily: typography.fontFamily.heading,
              fontWeight: 700,
              letterSpacing: typography.letterSpacing.display,
              color: color.text.primary,
            }}
          >
            Package status
          </Typography>
          <Typography variant="caption" sx={{ color: color.text.secondary }}>
            Click a card to select or deselect it for sync.
          </Typography>
        </Box>
        <ToolbarActions actions={toolbarActions} />
      </Box>
    </StickyChrome>
  );
}

function PackageGrid({ page }: { page: TerminologyPageState }) {
  if (page.loadingStatus || !page.status) return null;
  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" },
        gap: 2,
        mb: 3,
      }}
    >
      {PACKAGE_KEYS.map((key) =>
        page.status?.packages[key] ? (
          <PackageCard
            key={key}
            pkg={page.status.packages[key]}
            selected={page.selected.has(key)}
            onToggle={() => page.togglePackage(key)}
            disabled={page.syncing}
          />
        ) : null,
      )}
    </Box>
  );
}

function SyncControls({ page }: { page: TerminologyPageState }) {
  const idle = !page.syncing && page.selected.size > 0;
  return (
    <Box sx={syncBoxSx} data-testid="terminology-sync-controls">
      <Typography
        variant="subtitle1"
        sx={{
          fontFamily: typography.fontFamily.heading,
          fontWeight: 700,
          letterSpacing: typography.letterSpacing.display,
          color: color.text.primary,
          mb: 0.5,
        }}
      >
        Sync from TRUD
      </Typography>
      <Typography variant="body2" sx={{ mb: 1.5, fontSize: "0.85rem", color: color.text.secondary }}>
        {page.selected.size === 0
          ? "Select at least one package above to enable sync."
          : `${page.selected.size} package${page.selected.size === 1 ? "" : "s"} selected. The knowledge graph will update automatically after download.`}
      </Typography>
      <Stack direction="row" spacing={1.5}>
        <Button
          variant="contained"
          startIcon={
            page.syncing ? <CircularProgress size={16} color="inherit" /> : <DownloadingIcon />
          }
          onClick={page.startSync}
          disabled={!idle}
          sx={syncStartSx(idle)}
        >
          {page.syncing ? "Syncing..." : "Start sync"}
        </Button>
        {page.syncing ? (
          <Button
            variant="outlined"
            onClick={page.cancelSync}
            sx={{
              textTransform: "none",
              color: color.status.danger,
              borderColor: color.status.danger,
            }}
          >
            Cancel
          </Button>
        ) : null}
      </Stack>
    </Box>
  );
}

const syncBoxSx = {
  mt: 1,
  mb: 3,
  p: 2.25,
  borderRadius: 2,
  border: "1px solid " + color.text.secondary,
  bgcolor: color.surface.raised,
  boxShadow: elevation.card,
};

function syncStartSx(idle: boolean) {
  if (idle) {
    return {
      textTransform: "none",
      bgcolor: color.brand.primary,
      color: color.brand.onBrand,
      "&:hover": { bgcolor: color.brand.primaryHover },
    };
  }
  return {
    textTransform: "none",
    bgcolor: color.surface.divider,
    color: color.text.secondary,
    border: "1px solid " + color.text.secondary,
    opacity: 1,
    "&.Mui-disabled": {
      bgcolor: color.surface.divider,
      color: color.text.secondary,
      border: "1px solid " + color.text.secondary,
      opacity: 1,
    },
  };
}
