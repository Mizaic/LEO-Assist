"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import {
  deleteCodedLink,
  fetchEncounterCodedLinks,
  recodeCodedLink,
} from "@/lib/api";
import type { CodedLink, Correction, TermSearchResult } from "@/lib/types";
import TermSearch from "./TermSearch";

interface Props {
  patientId: string;
  encounterId: string;
  onCorrection: (c: Correction) => void;
  refreshTrigger?: number;
  onLinksChange?: (links: CodedLink[]) => void;
}

export default function CodedLinksSection({
  patientId,
  encounterId,
  onCorrection,
  refreshTrigger,
  onLinksChange,
}: Props) {
  const [links, setLinks] = useState<CodedLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [recodeTarget, setRecodeTarget] = useState<CodedLink | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  const refresh = refreshTrigger ?? 0;

  useEffect(() => {
    setLoading(true);
    fetchEncounterCodedLinks(patientId, encounterId)
      .then((data) => {
        setLinks(data);
        onLinksChange?.(data);
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Could not load coded links."),
      )
      .finally(() => setLoading(false));
  }, [patientId, encounterId, refresh, onLinksChange]);

  async function handleRemove(link: CodedLink) {
    if (!link.concept_id) return;
    setRemoving(link.concept_id);
    try {
      await deleteCodedLink(patientId, encounterId, link.concept_id);
      const next = links.filter((l) => l.concept_id !== link.concept_id);
      setLinks(next);
      onLinksChange?.(next);
      onCorrection({
        type: "remove",
        text: link.term ?? link.concept_id,
        detail: `Removed coded link ${link.concept_id}`,
        time: new Date().toISOString(),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed.");
    } finally {
      setRemoving(null);
    }
  }

  function handleRecodeSelect(result: TermSearchResult, modifiers?: { value?: string; unit?: string; reference_range?: string; interpretation?: string }, _context?: { negated?: boolean; uncertain?: boolean; historical?: boolean }) {
    if (!recodeTarget) return;
    const mods = modifiers && (modifiers.value || modifiers.unit || modifiers.reference_range || modifiers.interpretation)
      ? { value: modifiers.value, unit: modifiers.unit, reference_range: modifiers.reference_range, interpretation: modifiers.interpretation }
      : undefined;
    recodeCodedLink(patientId, encounterId, recodeTarget.concept_id, {
      new_concept_id: result.snomed_concept_id,
      term: result.term,
      read_code: result.read_code,
      semantic_tag: recodeTarget.semantic_tag ?? undefined,
      modifiers: mods,
    })
      .then(() => {
        const next = links.map((l) =>
          l.concept_id === recodeTarget.concept_id
            ? {
                ...l,
                concept_id: result.snomed_concept_id,
                term: result.term,
                read_code: result.read_code,
              }
            : l
        );
        setLinks(next);
        onLinksChange?.(next);
        onCorrection({
          type: "recode",
          text: `${recodeTarget.term ?? recodeTarget.concept_id} → ${result.term}`,
          detail: `Recoded to ${result.snomed_concept_id}`,
          time: new Date().toISOString(),
        });
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Recode failed."),
      )
      .finally(() => setRecodeTarget(null));
  }

  if (loading) {
    return (
      <Typography variant="body2" sx={{ p: 1.5, color: "text.secondary" }}>
        Loading coded links…
      </Typography>
    );
  }
  if (error) {
    return (
      <Typography variant="body2" sx={{ p: 1.5, color: "error.main" }}>
        {error}
      </Typography>
    );
  }

  return (
    <>
      <Box sx={{ borderTop: 1, borderColor: "divider", flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
        <Typography
          variant="overline"
          sx={{
            display: "block",
            fontWeight: 600,
            color: "text.secondary",
            px: 2,
            py: 1.5,
            borderBottom: 1,
            borderColor: "divider",
            flexShrink: 0,
          }}
        >
          Coded terms ({links.length})
        </Typography>
        <Box sx={{ flex: 1, minHeight: 0, overflowY: "auto", py: 1 }}>
          {links.length === 0 ? (
            <Typography variant="body2" sx={{ p: 2, color: "text.disabled" }}>
              No coded terms yet. Select text and click &quot;Code selection&quot; to add.
            </Typography>
          ) : (
            <List disablePadding>
              {links.map((link, idx) => (
                <Box key={link.concept_id}>
                  <ListItem
                    secondaryAction={
                      <Stack direction="row" spacing={0.5}>
                        <IconButton
                          size="small"
                          onClick={() => setRecodeTarget(link)}
                          title="Recode"
                        >
                          <EditIcon fontSize="small" />
                        </IconButton>
                        <IconButton
                          size="small"
                          color="error"
                          onClick={() => handleRemove(link)}
                          disabled={removing === link.concept_id}
                          title="Remove"
                        >
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Stack>
                    }
                    sx={{ px: 2, alignItems: "flex-start" }}
                  >
                    <ListItemText
                      primary={link.term ?? link.concept_id}
                      primaryTypographyProps={{ variant: "body2", fontWeight: 500, color: "text.secondary" }}
                      secondary={
                        <Box component="span">
                          {Boolean(
                            link.modifiers?.value != null ||
                              link.modifiers?.unit ||
                              link.modifiers?.reference_range ||
                              link.modifiers?.interpretation,
                          ) && (
                            <Typography component="span" variant="caption" sx={{ display: "block", color: "success.main", mb: 0.25 }}>
                              {[link.modifiers?.value, link.modifiers?.unit]
                                .filter((x): x is string | number => x != null && x !== "")
                                .map(String)
                                .join(" ")}
                              {link.modifiers?.reference_range ? (
                                <Typography component="span" variant="caption" sx={{ color: "text.secondary", ml: 0.75 }}>
                                  [{String(link.modifiers.reference_range)}]
                                </Typography>
                              ) : null}
                              {link.modifiers?.interpretation ? (
                                <Typography component="span" variant="caption" sx={{ color: "primary.main", ml: 0.75, fontWeight: 500 }}>
                                  {String(link.modifiers.interpretation)}
                                </Typography>
                              ) : null}
                            </Typography>
                          )}
                          <Typography component="span" variant="caption" sx={{ display: "block", fontFamily: "var(--font-mono)", color: "text.secondary" }}>
                            {link.concept_id}
                            {link.read_code && ` · ${link.read_code}`}
                          </Typography>
                        </Box>
                      }
                    />
                  </ListItem>
                  {idx < links.length - 1 && <Divider component="li" />}
                </Box>
              ))}
            </List>
          )}
        </Box>
      </Box>

      {recodeTarget && (
        <TermSearch
          onSelect={handleRecodeSelect}
          onClose={() => setRecodeTarget(null)}
          onCorrection={onCorrection}
          captureValueUnit
          confirmLabel="Recode"
          initialModifiers={
            recodeTarget.modifiers?.value != null || recodeTarget.modifiers?.unit || recodeTarget.modifiers?.reference_range || recodeTarget.modifiers?.interpretation
              ? {
                  value: recodeTarget.modifiers.value as string | number | undefined,
                  unit: recodeTarget.modifiers.unit as string | undefined,
                  reference_range: recodeTarget.modifiers.reference_range as string | undefined,
                  interpretation: recodeTarget.modifiers.interpretation as string | undefined,
                }
              : undefined
          }
        />
      )}
    </>
  );
}
