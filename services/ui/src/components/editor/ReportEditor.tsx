/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
'use client';

import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import Typography from '@mui/material/Typography';
import { DndContext, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { useEditorStore } from '@/stores/editorStore';
import { useOrgId } from '@/context/OrgContext';
import { Toolbar } from './Toolbar';
import { PageThumbnails } from './PageThumbnails';
import { ElementPalette } from './ElementPalette';
import { CanvasArea } from './CanvasArea';
import { PropertiesPanel } from './PropertiesPanel';
import {
  getMeasureReport,
  extractLayoutFromReport,
  getMeasures,
} from '@/lib/api';
import { DEFAULT_LAYOUT } from '@/lib/types/layout';
import { getTemplateById } from '@/lib/templates';
import type { Measure } from '@/lib/types/fhir';
import type { AgentInterpretation, AgentModelSize } from './agentTypes';
import type { PendingDrop } from './reportEditorHelpers';
import { useReportEditorHandlers } from './reportEditorHandlers';
import {
  MeasurePickerWrapper,
  AgentInterpretationDialog,
  InterpretationLinkDialog,
} from './ReportEditorDialogs';

// ── Props ────────────────────────────────────────────────────────────────────

interface ReportEditorProps {
  reportId?: string;
}

// ── Component ────────────────────────────────────────────────────────────────

export function ReportEditor({ reportId }: ReportEditorProps) {
  const searchParams = useSearchParams();
  const {
    initializeEditor,
    layout,
    report,
    setReport,
    setReportScope,
    setRuntimeParams,
  } = useEditorStore();
  const globalOrgId = useOrgId();

  // ── Local state ──────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(!!reportId && reportId !== 'new');
  const [isClient, setIsClient] = useState(false);
  const [saving, setSaving] = useState(false);
  const [measures, setMeasures] = useState<Measure[]>([]);
  const [isMeasureDialogOpen, setIsMeasureDialogOpen] = useState(false);
  const [isInterpretationDialogOpen, setIsInterpretationDialogOpen] = useState(false);
  const [measureSearchQuery, setMeasureSearchQuery] = useState('');
  const [pendingDrop, setPendingDrop] = useState<PendingDrop | null>(null);
  const [pendingInterpretationDrop, setPendingInterpretationDrop] = useState<PendingDrop | null>(null);
  const [selectedInterpretationLink, setSelectedInterpretationLink] = useState<string[]>([]);
  const [agentModelSize, setAgentModelSize] = useState<AgentModelSize>('small');
  const [agentDialogOpen, setAgentDialogOpen] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentSummary, setAgentSummary] = useState<AgentInterpretation | null>(null);
  const [agentGoal, setAgentGoal] = useState('');
  const [agentError, setAgentError] = useState<string | null>(null);

  // ── Handlers hook ────────────────────────────────────────────────────────
  const { handleSave, handleInterpret, handlePreview, handleExport, handleDragEnd } =
    useReportEditorHandlers({
      reportId,
      saving,
      agentModelSize,
      agentGoal,
      setSaving,
      setAgentError,
      setAgentSummary,
      setAgentBusy,
      setPendingDrop,
      setPendingInterpretationDrop,
      setIsMeasureDialogOpen,
      setIsInterpretationDialogOpen,
      setSelectedInterpretationLink,
    });

  // ── Effects ──────────────────────────────────────────────────────────────
  useEffect(() => {
    setIsClient(true);
    if (reportId && reportId !== 'new') {
      loadReport();
    } else {
      const templateId = searchParams?.get('template') ?? null;
      const tpl = templateId ? getTemplateById(templateId) : null;
      const initialLayout = tpl ? tpl.generate() : DEFAULT_LAYOUT;
      if (
        (initialLayout.reportScope === 'organization' || !initialLayout.reportScope) &&
        globalOrgId &&
        !initialLayout.runtimeParams?.organizationId
      ) {
        initialLayout.runtimeParams = {
          ...(initialLayout.runtimeParams || {}),
          organizationId: globalOrgId,
          organizationIds: [globalOrgId],
        };
      }
      initializeEditor(null, initialLayout);
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => { loadMeasures(); }, []);

  // ── Data loaders ─────────────────────────────────────────────────────────
  const loadReport = async () => {
    if (!reportId || reportId === 'new') return;
    setLoading(true);
    try {
      const fetchedReport = await getMeasureReport(reportId);
      const layoutJson = extractLayoutFromReport(fetchedReport);
      if (layoutJson && fetchedReport.subject?.reference && !layoutJson.runtimeParams?.subjectRef) {
        layoutJson.runtimeParams = {
          ...(layoutJson.runtimeParams || {}),
          subjectRef: fetchedReport.subject.reference,
        };
      }
      initializeEditor(fetchedReport, layoutJson || DEFAULT_LAYOUT);
    } catch (error) {
      console.error('Failed to load report:', error);
      initializeEditor(null, DEFAULT_LAYOUT);
    } finally {
      setLoading(false);
    }
  };

  const loadMeasures = async () => {
    try {
      const bundle = await getMeasures();
      const resources = (bundle.entry?.map((e) => e.resource).filter(Boolean) as Measure[]) || [];
      setMeasures(resources);
    } catch (error) {
      console.error('Failed to load measures:', error);
      setMeasures([]);
    }
  };

  // ── Simple callbacks ─────────────────────────────────────────────────────
  const handleScopeChange = useCallback(
    (scope: 'patient' | 'organization') => setReportScope(scope),
    [setReportScope],
  );

  // ── Derived ──────────────────────────────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
  );

  // ── Loading state ────────────────────────────────────────────────────────
  if (loading || !isClient) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
        <Box sx={{ textAlign: 'center' }}>
          <CircularProgress aria-label="Loading" />
          <Typography sx={{ mt: 2 }}>Loading editor...</Typography>
        </Box>
      </Box>
    );
  }

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <Box sx={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
        <Toolbar
          title={reportId && reportId !== 'new' ? 'Edit Report' : 'New Report'}
          onSave={handleSave}
          onPreview={handlePreview}
          onExport={handleExport}
          saving={saving}
          reportScope={layout.reportScope || 'organization'}
          onReportScopeChange={handleScopeChange}
          anchorOrganizationId={layout.runtimeParams?.organizationId || ''}
          onAnchorOrganizationIdChange={(organizationId) => {
            setRuntimeParams({ organizationId, organizationIds: organizationId ? [organizationId] : [] });
          }}
          anchorSubjectRef={layout.runtimeParams?.subjectRef || ''}
          onAnchorSubjectRefChange={(subjectRef) => setRuntimeParams({ subjectRef })}
          agentModelSize={agentModelSize}
          onAgentModelSizeChange={(size) => setAgentModelSize(size)}
          onInterpretMeasures={() => setAgentDialogOpen(true)}
          agentBusy={agentBusy}
          agentDisabled={saving}
        />
        <Box sx={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
          <Box
            sx={{
              width: '200px', bgcolor: 'background.paper', borderRight: 1,
              borderColor: 'divider', display: 'flex', flexDirection: 'column',
              overflowY: 'auto', overflowX: 'hidden',
            }}
          >
            <PageThumbnails />
            <ElementPalette />
          </Box>
          <CanvasArea />
          <Box
            sx={{
              width: '320px', minWidth: '320px', bgcolor: 'background.paper',
              borderLeft: 1, borderColor: 'divider', overflow: 'hidden',
            }}
          >
            <PropertiesPanel />
          </Box>
        </Box>
      </Box>

      {/* Dialogs */}
      <MeasurePickerWrapper
        open={isMeasureDialogOpen}
        measures={measures}
        pendingDrop={pendingDrop}
        onClose={() => setIsMeasureDialogOpen(false)}
        setPendingDrop={setPendingDrop}
      />
      <AgentInterpretationDialog
        open={agentDialogOpen}
        busy={agentBusy}
        goal={agentGoal}
        error={agentError}
        summary={agentSummary}
        onClose={() => setAgentDialogOpen(false)}
        onGoalChange={setAgentGoal}
        onRun={handleInterpret}
      />
      <InterpretationLinkDialog
        open={isInterpretationDialogOpen}
        measures={measures}
        pendingDrop={pendingInterpretationDrop}
        selectedLinks={selectedInterpretationLink}
        searchQuery={measureSearchQuery}
        agentModelSize={agentModelSize}
        setSelectedLinks={setSelectedInterpretationLink}
        setSearchQuery={setMeasureSearchQuery}
        onClose={() => {
          setIsInterpretationDialogOpen(false);
          setPendingInterpretationDrop(null);
          setMeasureSearchQuery('');
        }}
        onCancel={() => {
          setIsInterpretationDialogOpen(false);
          setPendingInterpretationDrop(null);
          setMeasureSearchQuery('');
        }}
      />
    </DndContext>
  );
}
