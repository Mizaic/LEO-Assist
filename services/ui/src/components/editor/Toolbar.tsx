'use client';

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Box from '@mui/material/Box';
import MuiToolbar from '@mui/material/Toolbar';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import TextField from '@mui/material/TextField';
import MenuItem from '@mui/material/MenuItem';
import Divider from '@mui/material/Divider';
import UndoOutlined from '@mui/icons-material/UndoOutlined';
import RedoOutlined from '@mui/icons-material/RedoOutlined';
import SaveOutlined from '@mui/icons-material/SaveOutlined';
import VisibilityOutlined from '@mui/icons-material/VisibilityOutlined';
import ZoomInOutlined from '@mui/icons-material/ZoomInOutlined';
import ZoomOutOutlined from '@mui/icons-material/ZoomOutOutlined';
import GridOnOutlined from '@mui/icons-material/GridOnOutlined';
import GridViewOutlined from '@mui/icons-material/GridViewOutlined';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import MoreHorizOutlined from '@mui/icons-material/MoreHorizOutlined';
import RefreshOutlined from '@mui/icons-material/RefreshOutlined';
import DownloadOutlined from '@mui/icons-material/DownloadOutlined';
import { useEditorStore } from '@/stores/editorStore';
import type { CohortFilters } from '@/lib/types/layout';
import { useOrganizationOptions, usePatientOptions, useCohortFilterValues } from './useToolbarData';
import { CohortFiltersDialog } from './CohortFiltersDialog';

// ── Props ────────────────────────────────────────────────────────────────────

export interface ToolbarProps {
  title?: string;
  onSave?: () => Promise<void>;
  onPreview?: () => void;
  onExport?: () => void;
  saving?: boolean;
  reportScope?: 'patient' | 'organization';
  onReportScopeChange?: (scope: 'patient' | 'organization') => void;
  anchorOrganizationId?: string;
  onAnchorOrganizationIdChange?: (organizationId: string) => void;
  anchorSubjectRef?: string;
  onAnchorSubjectRefChange?: (subjectRef: string) => void;
  agentModelSize?: 'small' | 'big';
  onAgentModelSizeChange?: (size: 'small' | 'big') => void;
  onInterpretMeasures?: () => void;
  agentBusy?: boolean;
  agentDisabled?: boolean;
}

// ── Component ────────────────────────────────────────────────────────────────

export function Toolbar({
  title = 'Report Editor',
  onSave,
  onPreview,
  onExport,
  saving = false,
  reportScope = 'organization',
  onReportScopeChange,
  anchorOrganizationId,
  onAnchorOrganizationIdChange,
  anchorSubjectRef,
  onAnchorSubjectRefChange,
  agentModelSize = 'small',
  onAgentModelSizeChange,
  onInterpretMeasures,
  agentBusy = false,
  agentDisabled = false,
}: ToolbarProps) {
  const router = useRouter();
  const isDev = process.env.NEXT_PUBLIC_ENVIRONMENT === 'development';
  const [isCohortDialogOpen, setIsCohortDialogOpen] = useState(false);

  const {
    zoom, baseZoom, zoomIn, zoomOut, resetZoom,
    showGrid, toggleGrid, snapToGrid, toggleSnapToGrid,
    undo, redo, canUndo, canRedo, isDirty,
    layout, setRuntimeParams,
  } = useEditorStore();

  const cohortFilters = layout.runtimeParams?.cohortFilters || {};

  const { orgQuery, setOrgQuery, orgOptionLabels } = useOrganizationOptions(isDev, reportScope);
  const { patientQuery, setPatientQuery, patientOptionLabels } = usePatientOptions(isDev, reportScope);
  const { cohortStatusValue, excludedStatusValue, cancerTypeValue } = useCohortFilterValues(cohortFilters);

  const handleBack = useCallback(() => router.push('/reports'), [router]);

  const handleSave = useCallback(async () => {
    if (onSave) await onSave();
  }, [onSave]);

  const handleRefreshData = useCallback(() => {
    setRuntimeParams({ refreshToken: Date.now() });
  }, [setRuntimeParams]);

  const updateCohortFilters = useCallback(
    (updates: Partial<CohortFilters>) => {
      setRuntimeParams({
        cohortFilters: { ...(layout.runtimeParams?.cohortFilters || {}), ...updates },
      });
    },
    [layout.runtimeParams, setRuntimeParams]
  );

  const clearCohortFilters = useCallback(() => {
    setRuntimeParams({ cohortFilters: {} });
  }, [setRuntimeParams]);

  const handleSubjectChange = useCallback(
    (value: string) => {
      if (!value) return onAnchorSubjectRefChange?.('');
      onAnchorSubjectRefChange?.(value.startsWith('Patient/') ? value : `Patient/${value}`);
    },
    [onAnchorSubjectRefChange]
  );

  return (
    <Box
      sx={{
        p: '8px 16px',
        borderBottom: 1,
        borderColor: 'divider',
        bgcolor: 'background.paper',
        display: 'flex',
        justifyContent: 'space-between',
      }}
    >
      {/* Left: back + title */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Tooltip title="Back to Reports">
          <IconButton onClick={handleBack} aria-label="Back to Reports">
            <ArrowBackOutlined />
          </IconButton>
        </Tooltip>
        <Typography sx={{ fontSize: '1rem', fontWeight: 600, ml: 1 }}>{title}</Typography>
        {isDirty && (
          <Tooltip title="Unsaved changes">
            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: 'warning.light', ml: 1 }} />
          </Tooltip>
        )}
      </Box>

      {/* Centre: undo/redo, zoom, grid */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        <MuiToolbar variant="dense" disableGutters sx={{ minHeight: 'auto', gap: 0 }}>
          <UndoRedoGroup undo={undo} redo={redo} canUndo={canUndo()} canRedo={canRedo()} />
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
          <ZoomGroup zoom={zoom} baseZoom={baseZoom} zoomIn={zoomIn} zoomOut={zoomOut} resetZoom={resetZoom} />
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />
          <GridGroup showGrid={showGrid} snapToGrid={snapToGrid} toggleGrid={toggleGrid} toggleSnapToGrid={toggleSnapToGrid} />
        </MuiToolbar>
      </Box>

      {/* Right: scope selectors, actions */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <ScopeSelector reportScope={reportScope} onReportScopeChange={onReportScopeChange} />

        {reportScope === 'organization' && (
          <OrgField
            isDev={isDev}
            orgQuery={orgQuery}
            setOrgQuery={setOrgQuery}
            orgOptionLabels={orgOptionLabels}
            anchorOrganizationId={anchorOrganizationId}
            onAnchorOrganizationIdChange={onAnchorOrganizationIdChange}
          />
        )}
        {reportScope === 'patient' && (
          <PatientField
            isDev={isDev}
            patientQuery={patientQuery}
            setPatientQuery={setPatientQuery}
            patientOptionLabels={patientOptionLabels}
            anchorSubjectRef={anchorSubjectRef}
            handleSubjectChange={handleSubjectChange}
          />
        )}

        <Tooltip title="Cohort filters">
          <Button variant="text" startIcon={<MoreHorizOutlined />} onClick={() => setIsCohortDialogOpen(true)}>
            Cohort
          </Button>
        </Tooltip>

        {onInterpretMeasures && (
          <InterpretSection
            agentModelSize={agentModelSize}
            onAgentModelSizeChange={onAgentModelSizeChange}
            onInterpretMeasures={onInterpretMeasures}
            agentBusy={agentBusy}
            agentDisabled={agentDisabled}
          />
        )}

        <Tooltip title="Refresh data">
          <Button variant="text" startIcon={<RefreshOutlined />} onClick={handleRefreshData}>Refresh</Button>
        </Tooltip>
        <Tooltip title="Preview">
          <Button variant="text" startIcon={<VisibilityOutlined />} onClick={onPreview}>Preview</Button>
        </Tooltip>
        {onExport && (
          <Tooltip title="Export PDF">
            <Button variant="text" startIcon={<DownloadOutlined />} onClick={onExport}>Export</Button>
          </Tooltip>
        )}
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress aria-label="Loading" size={16} color="inherit" /> : <SaveOutlined />}
          onClick={handleSave}
          disabled={saving || !isDirty}
        >
          {saving ? 'Saving...' : 'Save'}
        </Button>
      </Box>

      <CohortFiltersDialog
        open={isCohortDialogOpen}
        onClose={() => setIsCohortDialogOpen(false)}
        cohortFilters={cohortFilters}
        cohortStatusValue={cohortStatusValue}
        excludedStatusValue={excludedStatusValue}
        cancerTypeValue={cancerTypeValue}
        onUpdateCohortFilters={updateCohortFilters}
        onClearCohortFilters={clearCohortFilters}
      />
    </Box>
  );
}

// ── Small inline sub-components ──────────────────────────────────────────────

const dropdownColumnSx = { display: 'flex', flexDirection: 'column' as const, gap: 0.5, minWidth: '140px' };
const microLabelSx = { fontSize: '0.625rem', color: 'text.secondary' };

function UndoRedoGroup({ undo, redo, canUndo, canRedo }: { undo: () => void; redo: () => void; canUndo: boolean; canRedo: boolean }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Tooltip title="Undo (Ctrl+Z)">
        <span><IconButton aria-label="Undo" onClick={undo} disabled={!canUndo}><UndoOutlined /></IconButton></span>
      </Tooltip>
      <Tooltip title="Redo (Ctrl+Y)">
        <span><IconButton aria-label="Redo" onClick={redo} disabled={!canRedo}><RedoOutlined /></IconButton></span>
      </Tooltip>
    </Box>
  );
}

function ZoomGroup({ zoom, baseZoom, zoomIn, zoomOut, resetZoom }: { zoom: number; baseZoom: number; zoomIn: () => void; zoomOut: () => void; resetZoom: () => void }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Tooltip title="Zoom Out">
        <span><IconButton aria-label="Zoom out" onClick={zoomOut} disabled={zoom <= 0.25}><ZoomOutOutlined /></IconButton></span>
      </Tooltip>
      <Tooltip title="Click to reset zoom">
        <Button variant="text" onClick={resetZoom} sx={{ minWidth: '50px', fontSize: '0.75rem', color: 'text.secondary' }}>
          {Math.round((baseZoom ? zoom / baseZoom : zoom) * 100)}%
        </Button>
      </Tooltip>
      <Tooltip title="Zoom In">
        <span><IconButton aria-label="Zoom in" onClick={zoomIn} disabled={zoom >= 4}><ZoomInOutlined /></IconButton></span>
      </Tooltip>
    </Box>
  );
}

function GridGroup({ showGrid, snapToGrid, toggleGrid, toggleSnapToGrid }: { showGrid: boolean; snapToGrid: boolean; toggleGrid: () => void; toggleSnapToGrid: () => void }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Tooltip title={showGrid ? 'Hide Grid' : 'Show Grid'}>
        <IconButton aria-label={showGrid ? 'Hide grid' : 'Show grid'} onClick={toggleGrid} color={showGrid ? 'primary' : 'default'}><GridOnOutlined /></IconButton>
      </Tooltip>
      <Tooltip title={snapToGrid ? 'Disable Snap' : 'Enable Snap'}>
        <IconButton aria-label={snapToGrid ? 'Disable snap to grid' : 'Enable snap to grid'} onClick={toggleSnapToGrid} color={snapToGrid ? 'primary' : 'default'}><GridViewOutlined /></IconButton>
      </Tooltip>
    </Box>
  );
}

function ScopeSelector({ reportScope, onReportScopeChange }: { reportScope: string; onReportScopeChange?: (scope: 'patient' | 'organization') => void }) {
  return (
    <Box sx={dropdownColumnSx}>
      <Typography sx={microLabelSx}>Scope</Typography>
      <TextField select size="small" id="report-scope" value={reportScope} onChange={(e) => onReportScopeChange?.(e.target.value as 'patient' | 'organization')} aria-label="Report scope">
        <MenuItem value="organization">Organization</MenuItem>
        <MenuItem value="patient">Patient</MenuItem>
      </TextField>
    </Box>
  );
}

interface OrgFieldProps {
  isDev: boolean;
  orgQuery: string;
  setOrgQuery: (q: string) => void;
  orgOptionLabels: Array<{ id: string; label: string }>;
  anchorOrganizationId?: string;
  onAnchorOrganizationIdChange?: (id: string) => void;
}

function OrgField({ isDev, orgQuery, setOrgQuery, orgOptionLabels, anchorOrganizationId, onAnchorOrganizationIdChange }: OrgFieldProps) {
  return (
    <Box sx={dropdownColumnSx}>
      <Typography sx={microLabelSx}>Organization</Typography>
      {isDev ? (
        <>
          <TextField
            size="small"
            value={orgQuery}
            placeholder="Search organizations"
            inputProps={{ list: 'organization-options' }}
            onChange={(e) => {
              const nextValue = e.target.value || '';
              setOrgQuery(nextValue);
              const match = orgOptionLabels.find((o) => o.label === nextValue) || orgOptionLabels.find((o) => o.id === nextValue);
              onAnchorOrganizationIdChange?.(match?.id || '');
            }}
          />
          <datalist id="organization-options">
            {orgOptionLabels.map((opt) => <option key={opt.id} value={opt.label} />)}
          </datalist>
        </>
      ) : (
        <TextField size="small" value={anchorOrganizationId || ''} disabled placeholder="Organization is set at runtime" />
      )}
    </Box>
  );
}

interface PatientFieldProps {
  isDev: boolean;
  patientQuery: string;
  setPatientQuery: (q: string) => void;
  patientOptionLabels: Array<{ id: string; label: string }>;
  anchorSubjectRef?: string;
  handleSubjectChange: (value: string) => void;
}

function PatientField({ isDev, patientQuery, setPatientQuery, patientOptionLabels, anchorSubjectRef, handleSubjectChange }: PatientFieldProps) {
  return (
    <Box sx={dropdownColumnSx}>
      <Typography sx={microLabelSx}>Patient</Typography>
      {isDev ? (
        <>
          <TextField
            size="small"
            value={patientQuery}
            placeholder="Search patients"
            inputProps={{ list: 'patient-options' }}
            onChange={(e) => {
              const nextValue = e.target.value || '';
              setPatientQuery(nextValue);
              const match = patientOptionLabels.find((o) => o.label === nextValue) || patientOptionLabels.find((o) => o.id === nextValue);
              handleSubjectChange(match?.id || '');
            }}
          />
          <datalist id="patient-options">
            {patientOptionLabels.map((opt) => <option key={opt.id} value={opt.label} />)}
          </datalist>
        </>
      ) : (
        <TextField size="small" id="report-subject" value={anchorSubjectRef || ''} disabled placeholder="Patient is set at runtime" aria-label="Patient subject reference" />
      )}
    </Box>
  );
}

function InterpretSection({ agentModelSize, onAgentModelSizeChange, onInterpretMeasures, agentBusy, agentDisabled }: { agentModelSize: string; onAgentModelSizeChange?: (size: 'small' | 'big') => void; onInterpretMeasures: () => void; agentBusy: boolean; agentDisabled: boolean }) {
  return (
    <>
      <Box sx={dropdownColumnSx}>
        <Typography sx={microLabelSx}>Model</Typography>
        <TextField select size="small" value={agentModelSize} onChange={(e) => onAgentModelSizeChange?.(e.target.value as 'small' | 'big')} aria-label="Agent model size" disabled={agentBusy}>
          <MenuItem value="small">Small</MenuItem>
          <MenuItem value="big">Big</MenuItem>
        </TextField>
      </Box>
      <Tooltip title="Interpret measures">
        <Button variant="text" startIcon={agentBusy ? <CircularProgress aria-label="Loading" size={16} /> : undefined} onClick={onInterpretMeasures} disabled={agentBusy || agentDisabled}>
          {agentBusy ? 'Running...' : 'Interpret'}
        </Button>
      </Tooltip>
    </>
  );
}
