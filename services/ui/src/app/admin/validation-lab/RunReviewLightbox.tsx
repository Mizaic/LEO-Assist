/**
 * Primary Validation Lab run review lightbox.
 *
 * Atlas: DI-C953EF73 / DI-FE423B8D / DO-4FD76836
 */
"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Collapse from "@mui/material/Collapse";
import Dialog from "@mui/material/Dialog";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";

import { PipelineWizard } from "./inspector/PipelineWizard";
import { RunInspectorLogTab } from "./inspector/RunInspectorLogTab";
import { RunInspectorDataTab } from "./inspector/RunInspectorDataTab";
import { RunInspectorSummaryTab } from "./inspector/RunInspectorSummaryTab";
import { RunSheetSbarActions } from "./RunSheetSbar";
import LetterPane from "./LetterPane";
import MarkWrongDialog from "./MarkWrongDialog";
import InlineFixCards from "./InlineFixCards";
import {
  useLabRunInspector,
  useLabRunStagePoll,
} from "@/hooks/useLabRunInspector";
import { createFinding, listRunFindings } from "./labFindingsApi";
import {
  categoryLabel,
  stageFromStepId,
  type FindingCategory,
  type ValidationFinding,
} from "./findingTypes";
import { fixHref, isInlineFix } from "./fixRoutes";
import { promoteGold } from "./labApi";

export interface RunReviewTarget {
  title: string;
  caseId?: string;
  labRunId?: string;
  pipelineRunId?: string;
  referralText?: string;
  whyOpened?: string;
  gpNote?: string;
  pmhText?: string;
  status: string;
  terminal: boolean;
  readOnly?: boolean;
  previousHeadlines?: Record<string, string>;
  assessmentCaseId?: string;
}

interface Props {
  target: RunReviewTarget | null;
  onClose: () => void;
  onRetest?: (headlines: Record<string, string>) => void;
  onSavedGold?: () => void;
  onBuildTwin?: (phrases: string[]) => void;
}

export default function RunReviewLightbox({
  target,
  onClose,
  onRetest,
  onSavedGold,
  onBuildTwin,
}: Props) {
  if (!target) return null;
  return (
    <ReviewBody
      target={target}
      onClose={onClose}
      onRetest={onRetest}
      onSavedGold={onSavedGold}
      onBuildTwin={onBuildTwin}
    />
  );
}

function ReviewBody({
  target,
  onClose,
  onRetest,
  onSavedGold,
  onBuildTwin,
}: Omit<Props, "target"> & { target: RunReviewTarget }) {
  const caseId = target.caseId || "";
  const labRunId = target.labRunId || "";
  const pipelineRunId = target.pipelineRunId || "";
  const findingRunId = labRunId || pipelineRunId;
  const polledStages = useLabRunStagePoll(
    caseId,
    labRunId,
    Boolean(labRunId && caseId),
    target.terminal,
  );
  const inspector = useLabRunInspector({
    caseId,
    runId: labRunId,
    pipelineRunId,
    enabled: Boolean(labRunId || pipelineRunId),
    pollStages: polledStages,
    terminal: target.terminal,
  });
  const [tab, setTab] = useState(0);
  const [logOpen, setLogOpen] = useState(false);
  const [findings, setFindings] = useState<ValidationFinding[]>([]);
  const [markTarget, setMarkTarget] = useState("");
  const [fixCategory, setFixCategory] = useState<FindingCategory | "">("");
  const [goldNotice, setGoldNotice] = useState("");

  const reloadFindings = useCallback(async () => {
    if (!findingRunId) return;
    setFindings(await listRunFindings(findingRunId));
  }, [findingRunId]);

  useEffect(() => {
    void reloadFindings().catch(() => setFindings([]));
  }, [reloadFindings]);

  async function saveFinding(category: FindingCategory, note: string) {
    if (!findingRunId) return;
    const span = inspector.spans.find(
      (s) => s.step_id === inspector.selectedStepId,
    );
    await createFinding(findingRunId, {
      stage_id: stageFromStepId(span?.step_id || "extract"),
      category,
      target: markTarget,
      note,
    });
    setFixCategory(category);
    await reloadFindings();
  }

  async function onSaveGold() {
    if (!target.caseId || !labRunId) return;
    await promoteGold(target.caseId, labRunId);
    setGoldNotice("Saved as gold.");
    onSavedGold?.();
  }

  const selectedSpan = inspector.spans.find(
    (s) => s.step_id === inspector.selectedStepId,
  );
  const highlight = markTarget || selectedSpan?.work_preview?.items?.[0]?.text;

  return (
    <Dialog
      open
      onClose={onClose}
      fullWidth
      maxWidth={false}
      data-testid="validation-lab-run-review"
      PaperProps={{
        sx: {
          width: "min(1600px, 100%)",
          height: "min(920px, calc(100vh - 32px))",
          maxWidth: "none",
          m: 2,
        },
      }}
    >
      <Stack sx={{ height: "100%", minHeight: 0 }}>
        <ReviewHeader
          title={target.title}
          status={target.status}
          onClose={onClose}
          onRetest={
            onRetest
              ? () => {
                  const headlines: Record<string, string> = {};
                  for (const span of inspector.spans) {
                    headlines[span.step_id] = span.work_preview?.headline || "";
                  }
                  onRetest(headlines);
                }
              : undefined
          }
          onSaveGold={
            target.caseId && target.terminal && !target.readOnly
              ? () => void onSaveGold()
              : undefined
          }
          onBuildTwin={
            onBuildTwin
              ? () => onBuildTwin(findings.map((f) => f.target).filter(Boolean))
              : undefined
          }
        />
        {goldNotice ? (
          <Typography variant="body2" color="success.main" sx={{ px: 2 }}>
            {goldNotice}
          </Typography>
        ) : null}
        <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
          <LetterPane
            referralText={
              target.referralText || inspector.snapshot?.source_text || ""
            }
            openedBecause={target.whyOpened}
            highlight={highlight}
            gpNote={target.gpNote}
            pmhText={target.pmhText}
          />
          <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
            <Tabs value={tab} onChange={(_, v) => setTab(v)}>
              <Tab label="Pipeline" data-testid="validation-lab-review-tab-pipeline" />
              <Tab label="Data flow" />
              <Tab label="Summary" />
            </Tabs>
            <Box sx={{ flex: 1, minHeight: 0, overflow: "hidden" }}>
              {tab === 0 ? (
                <PipelineWizard
                  spans={inspector.spans}
                  selectedStepId={inspector.selectedStepId}
                  onSelectStep={inspector.setSelectedStepId}
                  stageDetail={inspector.stageDetail}
                  stageLoading={inspector.stageLoading}
                  previousHeadlines={target.previousHeadlines}
                  onFixInGuards={(span) => {
                    window.location.href = fixHref({
                      category: "guard",
                      firedRuleId: span.rule_id,
                      sourceSentence: span.source_sentence,
                      target: span.source_sentence,
                    });
                  }}
                  onMarkWrong={(text) => setMarkTarget(text)}
                />
              ) : null}
              {tab === 1 ? (
                <RunInspectorDataTab
                  spans={inspector.spans}
                  planSteps={inspector.snapshot?.plan_steps || []}
                  planEdges={inspector.snapshot?.plan_edges}
                  selectedStepId={inspector.selectedStepId}
                  onSelectStep={inspector.setSelectedStepId}
                  stageDetail={inspector.stageDetail}
                  loading={inspector.stageLoading}
                />
              ) : null}
              {tab === 2 ? (
                <RunInspectorSummaryTab
                  spans={inspector.spans}
                  planSteps={inspector.snapshot?.plan_steps || []}
                  selectedStepId={inspector.selectedStepId}
                  onSelectStep={inspector.setSelectedStepId}
                  stageDetail={inspector.stageDetail}
                  loading={inspector.stageLoading}
                />
              ) : null}
            </Box>
            <FindingsStrip findings={findings} />
            {fixCategory && isInlineFix(fixCategory) ? (
              <Box sx={{ p: 1.5 }}>
                <InlineFixCards
                  category={fixCategory}
                  target={markTarget}
                  firedRuleId={selectedSpan?.rule_id}
                />
              </Box>
            ) : null}
            {fixCategory && !isInlineFix(fixCategory) ? (
              <Box sx={{ p: 1.5 }}>
                <Button
                  size="small"
                  variant="contained"
                  href={fixHref({ category: fixCategory, target: markTarget })}
                  data-testid="validation-lab-fix-open"
                >
                  Fix {categoryLabel(fixCategory)}
                </Button>
              </Box>
            ) : null}
          </Box>
        </Box>
        <Box sx={{ borderTop: "1px solid", borderColor: "divider", px: 2, py: 1 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <Button size="small" onClick={() => setLogOpen((v) => !v)}>
              {logOpen ? "Hide live log" : "Show live log"}
            </Button>
            {target.assessmentCaseId || target.caseId ? (
              <RunSheetSbarActions
                sheet={{
                  caseId: target.assessmentCaseId || target.caseId || "",
                  title: target.title,
                  runId: labRunId,
                  status: target.status,
                }}
              />
            ) : null}
          </Stack>
          <Collapse in={logOpen}>
            <RunInspectorLogTab
              events={inspector.events}
              terminal={target.terminal}
              runStatus={target.status}
            />
          </Collapse>
        </Box>
      </Stack>
      <MarkWrongDialog
        open={Boolean(markTarget)}
        target={markTarget}
        onClose={() => setMarkTarget("")}
        onSave={saveFinding}
      />
    </Dialog>
  );
}

function ReviewHeader({
  title,
  status,
  onClose,
  onRetest,
  onSaveGold,
  onBuildTwin,
}: {
  title: string;
  status: string;
  onClose: () => void;
  onRetest?: () => void;
  onSaveGold?: () => void;
  onBuildTwin?: () => void;
}) {
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={1}
      sx={{ px: 2, py: 1.5, borderBottom: "1px solid", borderColor: "divider" }}
    >
      <Box sx={{ flex: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>
          {title}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {status}
        </Typography>
      </Box>
      {onRetest ? (
        <Button size="small" onClick={onRetest} data-testid="validation-lab-retest">
          Retest
        </Button>
      ) : null}
      {onSaveGold ? (
        <Button
          size="small"
          variant="contained"
          onClick={onSaveGold}
          data-testid="validation-lab-save-gold"
        >
          Save gold
        </Button>
      ) : null}
      {onBuildTwin ? (
        <Button size="small" onClick={onBuildTwin}>
          Build a synthetic twin
        </Button>
      ) : null}
      <IconButton onClick={onClose} aria-label="Close review">
        <CloseIcon />
      </IconButton>
    </Stack>
  );
}

function FindingsStrip({ findings }: { findings: ValidationFinding[] }) {
  if (!findings.length) return null;
  return (
    <Box sx={{ px: 2, py: 1, bgcolor: "#FFF7ED" }} data-testid="validation-lab-findings">
      <Typography variant="caption" fontWeight={700}>
        Open findings
      </Typography>
      {findings.map((f) => (
        <Typography key={f.id} variant="caption" display="block">
          {categoryLabel(f.category)} -- {f.target || f.note || f.stage_id}
        </Typography>
      ))}
    </Box>
  );
}
