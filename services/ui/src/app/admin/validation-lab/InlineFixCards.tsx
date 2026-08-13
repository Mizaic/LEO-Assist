/**
 * In-lab phrase mapping and cleaning-rule fix cards.
 *
 * Atlas: DI-562F2C9E / DO-4FD76836
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { savePhraseDraft } from "@/app/settings/surface-forms/phraseMappingsApi";
import { fixHref } from "./fixRoutes";
import type { FindingCategory } from "./findingTypes";

interface Props {
  category: FindingCategory | string;
  target: string;
  firedRuleId?: string;
  onRouted?: () => void;
}

export default function InlineFixCards({
  category,
  target,
  firedRuleId,
  onRouted,
}: Props) {
  if (category === "phrase_mapping") {
    return <PhraseFixCard target={target} onRouted={onRouted} />;
  }
  if (category === "guard") {
    return (
      <GuardFixCard
        target={target}
        firedRuleId={firedRuleId}
        onRouted={onRouted}
      />
    );
  }
  return null;
}

function PhraseFixCard({
  target,
  onRouted,
}: {
  target: string;
  onRouted?: () => void;
}) {
  const [conceptId, setConceptId] = useState("");
  const [term, setTerm] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await savePhraseDraft({
        phrase_key: target,
        action: "map",
        concept_id: conceptId,
        concept_term: term,
        reason: "Validation Lab mark as wrong",
      });
      setNotice("Draft phrase mapping saved. Submit it from Phrase mappings.");
      onRouted?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save mapping.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1 }}
      data-testid="validation-lab-inline-phrase"
    >
      <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
        Save a phrase mapping
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Map "{target}" to the right medical code. This stays a draft until review.
      </Typography>
      <Stack spacing={1}>
        <TextField
          size="small"
          label="SNOMED code"
          value={conceptId}
          onChange={(e) => setConceptId(e.target.value)}
        />
        <TextField
          size="small"
          label="Code name"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            variant="contained"
            disabled={busy || !conceptId}
            onClick={() => void save()}
          >
            Save draft
          </Button>
          <Button
            size="small"
            href={fixHref({ category: "phrase_mapping", target })}
          >
            Open Phrase mappings
          </Button>
        </Stack>
        {notice ? <Alert severity="success">{notice}</Alert> : null}
        {error ? <Alert severity="error">{error}</Alert> : null}
      </Stack>
    </Box>
  );
}

function GuardFixCard({
  target,
  firedRuleId,
  onRouted,
}: {
  target: string;
  firedRuleId?: string;
  onRouted?: () => void;
}) {
  const href = fixHref({
    category: "guard",
    target,
    firedRuleId,
    sourceSentence: target,
  });
  return (
    <Box
      sx={{ p: 1.5, border: "1px solid", borderColor: "divider", borderRadius: 1 }}
      data-testid="validation-lab-inline-guard"
    >
      <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
        Fix the cleaning rule
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Open Pipeline Guards with this sentence filled in. Add an exception if
        the rule should not fire.
      </Typography>
      <Button
        size="small"
        variant="contained"
        href={href}
        onClick={() => onRouted?.()}
      >
        Open Pipeline Guards
      </Button>
    </Box>
  );
}
