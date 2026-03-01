"use client";

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import DeleteIcon from "@mui/icons-material/Delete";
import type { Correction, EncounterTerm } from "@/lib/types";

interface Props {
  terms: EncounterTerm[];
  selectedId: string | null;
  onSelect: (termId: string) => void;
  onRemove?: (termId: string) => void;
  onCorrection?: (c: Correction) => void;
}

export default function EntitySidebar({ terms, selectedId, onSelect, onRemove, onCorrection }: Props) {
  return (
    <Box>
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
        }}
      >
        Clinical Terms ({terms.length})
      </Typography>
      <List disablePadding sx={{ overflowY: "auto", maxHeight: "calc(100vh - 320px)" }}>
        {terms.map((t) => {
          const score = Math.round((t.extraction_confidence ?? 0) * 100);
          const scoreColor =
            score >= 80 ? "success.main" : score >= 50 ? "warning.main" : "error.main";
          const isSelected = t.term_id === selectedId;

          return (
            <ListItem
              key={`${t.term_id}-${t.span_start}-${t.span_end}`}
              disablePadding
              secondaryAction={
                onRemove ? (
                  <IconButton
                    size="small"
                    color="error"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCorrection?.({
                        type: "remove",
                        text: t.text,
                        detail: `Removed clinical term`,
                        time: new Date().toISOString(),
                      });
                      onRemove(t.term_id);
                    }}
                    title="Remove term"
                    sx={{ mr: 0.5 }}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                ) : null
              }
              sx={{ borderBottom: 1, borderColor: "grey.100" }}
            >
              <ListItemButton
                selected={isSelected}
                onClick={() => onSelect(t.term_id)}
                sx={{
                  display: "block",
                  px: 2,
                  py: 1.25,
                }}
              >
              <Typography variant="body2" sx={{ fontWeight: 500, color: "text.primary", mb: 0.25 }}>
                {t.text}
              </Typography>
              {t.coding.snomed_term && (
                <Typography variant="caption" sx={{ color: "text.secondary", lineHeight: 1.3, mb: 0.25, display: "block" }}>
                  {t.coding.snomed_term}
                </Typography>
              )}
              <Box sx={{ display: "flex", alignItems: "center" }}>
                <Typography
                  variant="caption"
                  sx={{ color: "text.secondary", fontFamily: "var(--font-mono)", flex: 1 }}
                >
                  {t.coding.snomed_concept_id || t.coding.read_code || "unlinked"}
                </Typography>
                <Typography variant="caption" sx={{ color: scoreColor, fontWeight: 600 }}>
                  {score}%
                </Typography>
              </Box>
              {(t.context.negated || t.context.uncertain || t.context.historical) && (
                <Stack direction="row" spacing={0.5} sx={{ mt: 0.5 }}>
                  {t.context.negated && (
                    <Chip label="NEG" size="small" color="error" sx={{ height: 18, fontSize: 10 }} />
                  )}
                  {t.context.uncertain && (
                    <Chip label="UNC" size="small" color="warning" sx={{ height: 18, fontSize: 10 }} />
                  )}
                  {t.context.historical && (
                    <Chip label="Hx" size="small" color="secondary" sx={{ height: 18, fontSize: 10 }} />
                  )}
                </Stack>
              )}
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>
    </Box>
  );
}
