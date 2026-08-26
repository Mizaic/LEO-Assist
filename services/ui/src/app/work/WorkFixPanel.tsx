/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-E7824FED
 *   DI: DI-4A012A59, DI-6BD7B681
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-E7824FED")
 */
"use client";

import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import { EngineerBody, EngineerHeader, EngineerStepBar } from "./EngineerPanes";
import { deployWorkPhrase, submitWorkPhrase, type WorkFixKind } from "./workFixApi";
import { useEngineerPanel } from "./useEngineerPanel";

export type { WorkFixKind };

export interface WorkFixPanelProps {
  entityText: string;
  entityLabel?: string;
  reviewId?: string | null;
  encounterText?: string;
  extractionSource?: string;
  failureKind?: string;
  onFixed?: (kind: WorkFixKind) => void;
}

export default function WorkFixPanel(props: WorkFixPanelProps) {
  const panel = useEngineerPanel(props);
  return (
    <EngineerShell
      panel={panel}
      entityText={props.entityText}
      failureKind={props.failureKind}
    />
  );
}

function EngineerShell({
  panel,
  entityText,
  failureKind,
}: {
  panel: ReturnType<typeof useEngineerPanel>;
  entityText: string;
  failureKind?: string;
}) {
  const phrase = panel.phrase || entityText;
  return (
    <Stack
      spacing={1.5}
      sx={{
        mt: 2,
        p: 1.5,
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1,
        bgcolor: "action.hover",
      }}
      data-testid="work-fix-panel"
    >
      <EngineerHeader />
      <TextField
        size="small"
        label="Phrase"
        value={panel.phrase}
        onChange={(event) => panel.setPhrase(event.target.value)}
      />
      <EngineerStepBar step={panel.step} onSelect={panel.setStep} />
      <EngineerBody
        step={panel.step}
        mode={panel.mode}
        phrase={panel.phrase}
        entityText={entityText}
        entityLabel={panel.entityLabel}
        reviewId={panel.reviewId}
        encounterText={panel.encounterText}
        contextPhrase={panel.contextPhrase}
        category={panel.category}
        direction={panel.direction}
        busy={panel.busy}
        row={panel.row}
        failureKind={failureKind}
        onSelectMode={panel.setMode}
        onContextPhraseChange={panel.setContextPhrase}
        onCategoryChange={panel.setCategory}
        onDirectionChange={panel.setDirection}
        onIdle={() => panel.setMode("idle")}
        onRunFix={(kind, action) => runFix(panel, kind, action)}
        onSubmit={() =>
          void panel.runAction(
            () => submitWorkPhrase(phrase),
            "Submitted for review. A different person can publish.",
          )
        }
        onDeploy={(reason) =>
          void panel.runAction(
            () => deployWorkPhrase(phrase, reason),
            "Published. Live coding will use this fix.",
          )
        }
      />
      {panel.notice ? <Alert severity="success">{panel.notice}</Alert> : null}
      {panel.error ? <Alert severity="error">{panel.error}</Alert> : null}
    </Stack>
  );
}

function runFix(
  panel: ReturnType<typeof useEngineerPanel>,
  kind: WorkFixKind,
  action: () => Promise<void>,
) {
  const done =
    kind === "teach"
      ? "Saved. This teaching example can help the next similar letter."
      : kind === "context"
        ? "Saved. This cue is live now."
        : "Saved as a draft. Submit it for review next.";
  return panel.runAction(action, done).then(() => {
    panel.setMode("idle");
    panel.onFixed?.(kind);
  });
}
