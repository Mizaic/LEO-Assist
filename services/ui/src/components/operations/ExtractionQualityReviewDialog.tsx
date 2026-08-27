/**
 * In-place extraction quality review surface for the Validation Lab.
 * Letter with live highlights on the left; structured fact editor on the right.
 *
 * Atlas trace: DI-4A012A59 / DO-E7824FED
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import SchoolIcon from "@mui/icons-material/School";

import ExtractionReviewHeader from "./ExtractionReviewHeader";
import FormSchemaAnnotator from "./FormSchemaAnnotator";
import type { FormSchemaSection } from "./formSchemaDetector";
import {
  cleanLetterSelectionText,
  regionsFromSections,
  matchSectionFromLetterText,
} from "./formSchemaSectionFocus";
import { useTeachFormSectionFocus } from "./useTeachFormSectionFocus";

import LetterMarkdownView from "@/app/admin/validation-lab/LetterMarkdownView";
import { LetterMarkLegend } from "@/app/admin/validation-lab/LetterMarks";
import WorkCancelDialog from "@/app/work/WorkCancelDialog";
import WorkFixPanel from "@/app/work/WorkFixPanel";
import { EMPTY_LETTER_COPY } from "./extractionReviewCopy";
import { focusedReviewMarks } from "./extractionReviewHighlight";
import {
  FactList,
  draftExtractor,
  type DocumentQuality,
  type DraftEntity,
} from "./ExtractionReviewFacts";

interface ReviewData {
  sourceText: string;
  entities: DraftEntity[];
  quality: DocumentQuality;
  reason: string;
  formFingerprint: string;
  nhsNumber: string;
  ubrn: string;
  organization_id: string;
  service_id: string;
}

interface Props {
  taskId: string;
  open: boolean;
  onClose: () => void;
  onUnlocked: () => void;
}

// -- main component ---------------------------------------------------------

export default function ExtractionQualityReviewDialog({
  taskId,
  open,
  onClose,
  onUnlocked,
}: Props) {
  const [data, setData] = useState<ReviewData | null>(null);
  const [entities, setEntities] = useState<DraftEntity[]>([]);
  const [pickedText, setPickedText] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [rightTab, setRightTab] = useState<"facts" | "teach">("facts");
  const [teachSections, setTeachSections] = useState<FormSchemaSection[]>([]);
  const [pendingSelection, setPendingSelection] = useState<{
    pattern: string;
    entity_text: string;
    sectionId: string;
  } | null>(null);
  const [selectionHint, setSelectionHint] = useState("");
  const teachFocus = useTeachFormSectionFocus();

  useEffect(() => {
    if (!open || !taskId) return;
    setError("");
    setData(null);
    fetch(`/api/operations/extraction-reviews/${taskId}`, {
      credentials: "include",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then((res) => {
        if (!res.ok) throw new Error("load");
        return res.json() as Promise<Record<string, unknown>>;
      })
      .then((raw) => {
        const loaded: ReviewData = {
          sourceText: String(raw.source_text ?? ""),
          entities: Array.isArray(raw.draft_entities) ? (raw.draft_entities as DraftEntity[]) : [],
          quality: (raw.document_quality as DocumentQuality) ?? {},
          reason: String(raw.reason ?? ""),
          formFingerprint: String(
            (raw.document_quality as DocumentQuality | undefined)?.form_fingerprint_id ?? "",
          ),
          nhsNumber: String(raw.nhs_number ?? ""),
          ubrn: String(raw.ubrn ?? ""),
          organization_id: String(raw.organization_id ?? ""),
          service_id: String(raw.service_id ?? ""),
        };
        setData(loaded);
        setEntities(loaded.entities);
        setPickedText(loaded.entities[0]?.text ?? "");
      })
      .catch(() => setError("Could not load the letter. Try again."));
  }, [open, taskId]);

  function addSelection() {
    const text = window.getSelection()?.toString().trim() ?? "";
    if (!text) return;
    setEntities((prev) =>
      prev.some((e) => e.text === text)
        ? prev
        : [...prev, { text, semantic_tag: "", assertion: "present" }],
    );
  }

  function handleTeachSelection() {
    const raw = window.getSelection()?.toString().trim() ?? "";
    if (!raw) return;
    const cleaned = cleanLetterSelectionText(raw);
    const pattern = cleaned || raw;
    const focusedSection = teachSections.find(
      (s) => s.section_id === teachFocus.focusedSectionId,
    );
    if (focusedSection) {
      setPendingSelection({
        pattern,
        entity_text: pattern,
        sectionId: focusedSection.section_id,
      });
      setSelectionHint("");
      return;
    }
    const matched = matchSectionFromLetterText(teachSections, raw);
    if (matched) {
      teachFocus.selectSection(matched);
      setPendingSelection({
        pattern,
        entity_text: pattern,
        sectionId: matched.section_id,
      });
      setSelectionHint("");
      return;
    }
    setSelectionHint("Select a section card on the right first, then highlight text.");
    setTimeout(() => setSelectionHint(""), 4000);
  }

  function removeEntity(text: string) {
    setEntities((prev) => prev.filter((e) => e.text !== text));
  }

  function patchEntity(text: string, patch: Partial<DraftEntity>) {
    setEntities((prev) => prev.map((e) => (e.text === text ? { ...e, ...patch } : e)));
  }

  async function unlock() {
    setBusy(true);
    setError("");
    try {
      const res = await fetch("/api/operations/extraction-reviews/complete", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({
          task_id: taskId,
          source_text: data?.sourceText ?? "",
          reviewed_entities: entities,
          resolved_by: "validation_lab",
        }),
      });
      if (!res.ok) throw new Error("complete");
      onUnlocked();
    } catch {
      setError("Could not unlock the referral. Check the facts and try again.");
    } finally {
      setBusy(false);
    }
  }

  const focusTerm = pickedText || entities[0]?.text || "";
  const marks = focusedReviewMarks(entities, focusTerm);
  const score = data?.quality.document_quality_score ?? 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth={false}
      data-testid="extraction-quality-review-dialog"
      PaperProps={{
        sx: {
          width: "min(1400px, 100%)",
          height: "min(900px, calc(100vh - 32px))",
          maxWidth: "none",
          m: 2,
        },
      }}
    >
      <Stack sx={{ height: "100%", minHeight: 0 }}>
        <ExtractionReviewHeader
          reason={data?.reason ?? ""}
          qualityReasons={data?.quality.quality_reasons ?? []}
          score={score}
          loaded={Boolean(data)}
          nhsNumber={data?.nhsNumber ?? ""}
          ubrn={data?.ubrn ?? ""}
          onClose={onClose}
          onRemoveTask={() => setCancelOpen(true)}
        />
        <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
          <ReviewLetterPane
            sourceText={data?.sourceText ?? ""}
            marks={marks}
            focusTerm={focusTerm}
            onAddSelection={addSelection}
            onTeachSelection={handleTeachSelection}
            selectionHint={selectionHint}
            teachMode={rightTab === "teach"}
            highlightedRegionId={teachFocus.highlightedRegionId}
            sectionRegions={regionsFromSections(teachSections)}
            onSelectRegion={(regionId, clickedText) =>
              teachFocus.selectLetterText(teachSections, clickedText || regionId)
            }
          />
          <ReviewRightPane
            tab={rightTab}
            onTabChange={setRightTab}
            fingerprint={data?.formFingerprint ?? ""}
            sourceText={data?.sourceText ?? ""}
            onSchemaSaved={onUnlocked}
            focusedSectionId={teachFocus.focusedSectionId}
            onSelectSection={teachFocus.selectSection}
            onSectionsChange={setTeachSections}
            pendingSelection={pendingSelection}
            onPendingConsumed={() => setPendingSelection(null)}
            initialOrganizationId={data?.organization_id ?? ""}
            initialServiceId={data?.service_id ?? ""}
          >
            <ReviewFactsPane
              entities={entities}
              error={error}
              busy={busy}
              encounterText={data?.sourceText ?? ""}
              pickedText={focusTerm}
              onPick={setPickedText}
              onRemove={removeEntity}
              onPatch={patchEntity}
              onBack={onClose}
              onUnlock={() => void unlock()}
            />
          </ReviewRightPane>
        </Box>
      </Stack>
      {cancelOpen ? (
        <WorkCancelDialog
          taskId={taskId}
          onClose={() => setCancelOpen(false)}
          onCancelled={onUnlocked}
        />
      ) : null}
    </Dialog>
  );
}

// -- ReviewLetterPane -------------------------------------------------------

function ReviewLetterPane({
  sourceText,
  marks,
  focusTerm,
  onAddSelection,
  onTeachSelection,
  selectionHint,
  teachMode,
  highlightedRegionId,
  sectionRegions,
  onSelectRegion,
}: {
  sourceText: string;
  marks: ReturnType<typeof focusedReviewMarks>;
  focusTerm: string;
  onAddSelection: () => void;
  onTeachSelection: () => void;
  selectionHint: string;
  teachMode: boolean;
  highlightedRegionId: string | null;
  sectionRegions: ReturnType<typeof regionsFromSections>;
  onSelectRegion: (regionId: string, clickedText: string) => void;
}) {
  const hasLetter = Boolean(sourceText.trim());
  const letterRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = letterRef.current?.querySelector("[data-review-focus='true']");
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [focusTerm, sourceText]);
  useEffect(() => {
    if (!highlightedRegionId) return;
    const highlighted = letterRef.current?.querySelector(
      "[data-section-highlight='true']",
    );
    const fallback = letterRef.current?.querySelector(
      `[data-section-region="${highlightedRegionId}"]`,
    );
    const node = highlighted ?? fallback;
    if (node instanceof HTMLElement) {
      node.scrollIntoView?.({ block: "center", behavior: "smooth" });
    }
  }, [highlightedRegionId, sourceText]);
  return (
    <Box
      sx={{
        width: { xs: "100%", md: "42%" },
        minWidth: 280,
        borderRight: "1px solid",
        borderColor: "divider",
        display: "flex",
        flexDirection: "column",
        bgcolor: "grey.50",
        minHeight: 0,
      }}
    >
      <Box
        sx={{
          px: 2,
          py: 0.75,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "action.hover",
        }}
      >
        <Typography variant="caption" fontWeight={700} color="primary.main">
          {hasLetter && teachMode
            ? "Highlight text on the letter to add it as a label pattern"
            : hasLetter
              ? focusTerm
                ? "Numbers mark each time this fact appears. Select other text to add a fact."
                : "Select any text on the letter to add it as a fact"
              : "Letter"}
        </Typography>
        {selectionHint ? (
          <Typography
            variant="caption"
            color="warning.main"
            sx={{ display: "block", mt: 0.5 }}
            role="alert"
            data-testid="teach-selection-hint"
          >
            {selectionHint}
          </Typography>
        ) : null}
      </Box>
      <Box
        ref={letterRef}
        sx={{ flex: 1, overflow: "auto", p: 2, cursor: hasLetter ? "text" : "default" }}
        onMouseUp={
          hasLetter ? (teachMode ? onTeachSelection : onAddSelection) : undefined
        }
        data-testid="extraction-quality-letter"
        data-highlighted-region={highlightedRegionId ?? ""}
      >
        {hasLetter ? <LetterMarkLegend marks={marks} /> : null}
        <LetterMarkdownView
          text={sourceText}
          marks={marks}
          focusTerm={focusTerm}
          emptyLabel={EMPTY_LETTER_COPY}
          sectionRegions={teachMode ? sectionRegions : []}
          highlightedRegionId={teachMode ? highlightedRegionId : null}
          onSelectRegion={onSelectRegion}
        />
      </Box>
    </Box>
  );
}

// -- ReviewRightPane (tab shell) --------------------------------------------

function ReviewRightPane({
  tab,
  onTabChange,
  fingerprint,
  sourceText,
  onSchemaSaved,
  focusedSectionId,
  onSelectSection,
  onSectionsChange,
  pendingSelection,
  onPendingConsumed,
  initialOrganizationId,
  initialServiceId,
  children,
}: {
  tab: "facts" | "teach";
  onTabChange: (v: "facts" | "teach") => void;
  fingerprint: string;
  sourceText: string;
  onSchemaSaved: () => void;
  focusedSectionId: string | null;
  onSelectSection: (section: FormSchemaSection) => void;
  onSectionsChange: (sections: FormSchemaSection[]) => void;
  pendingSelection: { pattern: string; entity_text: string; sectionId: string } | null;
  onPendingConsumed: () => void;
  initialOrganizationId?: string;
  initialServiceId?: string;
  children: React.ReactNode;
}) {
  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      <Tabs
        value={tab}
        onChange={(_e, v: "facts" | "teach") => onTabChange(v)}
        sx={{ px: 2, borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}
        textColor="primary"
        indicatorColor="primary"
      >
        <Tab label="Review facts" value="facts" sx={{ minHeight: 40, textTransform: "none" }} />
        <Tab
          label="Teach this form"
          value="teach"
          icon={<SchoolIcon sx={{ fontSize: 16 }} />}
          iconPosition="start"
          sx={{ minHeight: 40, textTransform: "none" }}
        />
      </Tabs>
      {tab === "facts" ? (
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
          {children}
        </Box>
      ) : (
        <Box sx={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
          <FormSchemaAnnotator
            fingerprint={fingerprint}
            sourceText={sourceText}
            onSaved={onSchemaSaved}
            focusedSectionId={focusedSectionId}
            onSelectSection={onSelectSection}
            onSectionsChange={onSectionsChange}
            pendingSelection={pendingSelection}
            onPendingConsumed={onPendingConsumed}
            initialOrganizationId={initialOrganizationId}
            initialServiceId={initialServiceId}
          />
        </Box>
      )}
    </Box>
  );
}

// -- ReviewFactsPane --------------------------------------------------------

function ReviewFactsPane({
  entities,
  error,
  busy,
  encounterText,
  pickedText,
  onPick,
  onRemove,
  onPatch,
  onBack,
  onUnlock,
}: {
  entities: DraftEntity[];
  error: string;
  busy: boolean;
  encounterText: string;
  pickedText: string;
  onPick: (text: string) => void;
  onRemove: (text: string) => void;
  onPatch: (text: string, patch: Partial<DraftEntity>) => void;
  onBack: () => void;
  onUnlock: () => void;
}) {
  const picked = entities.find((entity) => entity.text === pickedText) ?? entities[0];
  return (
    <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
      {error ? (
        <Box
          sx={{
            px: 2,
            py: 1,
            bgcolor: "error.light",
            borderBottom: "1px solid",
            borderColor: "error.main",
            flexShrink: 0,
          }}
        >
          <Typography variant="body2" color="error">
            {error}
          </Typography>
        </Box>
      ) : null}
      <Box sx={{ flex: 1, overflow: "auto", p: 2 }}>
        <FactList
          entities={entities}
          letterText={encounterText}
          pickedText={picked?.text ?? ""}
          onPick={onPick}
          onRemove={onRemove}
          onPatch={onPatch}
        />
        {picked ? (
          <WorkFixPanel
            entityText={picked.text}
            entityLabel={picked.semantic_tag}
            encounterText={encounterText}
            extractionSource={draftExtractor(picked)}
          />
        ) : null}
      </Box>
      <Stack
        direction="row"
        spacing={1}
        justifyContent="flex-end"
        sx={{
          px: 2,
          py: 1.5,
          borderTop: "1px solid",
          borderColor: "divider",
          bgcolor: "#FAFAFA",
          flexShrink: 0,
        }}
      >
        <Button onClick={onBack} disabled={busy} size="small">
          Back
        </Button>
        <Button
          variant="contained"
          onClick={onUnlock}
          disabled={busy || entities.length === 0}
          size="small"
        >
          {busy ? "Unlocking..." : "Approve and unlock"}
        </Button>
      </Stack>
    </Box>
  );
}
