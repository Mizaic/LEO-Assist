/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-42246DA7")
 */
"use client";

/**
 * "Blocked codes" section of the synonym-chip editor (SynonymChipEditor.tsx).
 *
 * A blocked code is stored as a bare SNOMED id (``LogicCriterion.
 * excluded_concept_ids``) with no cached term, so a reviewer auditing the
 * rule previously only ever saw "code 309737007" -- unreadable without a
 * SNOMED browser open in another tab.
 *
 * This resolves each id's preferred term via the exact-id-match branch of
 * the existing search endpoint (``MATCH (c:Concept {id: $q})`` in
 * ``TERMINOLOGY_SEARCH``, services/api/app/models/neo4j_schema.py) and
 * shows the friendly term on the chip. The raw code stays available in a
 * tooltip so the id is never lost for audit purposes, and unresolved codes
 * (search miss, network error) fall back to the old "code {id}" label.
 */

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import BlockIcon from "@mui/icons-material/Block";
import CloseIcon from "@mui/icons-material/Close";

import { friendlyTerm } from "./copy";
import type { ConceptSearchHit, NodeUpdate } from "./types";

interface Props {
  nodeId: string;
  excluded: string[];
  onUpdate: (u: NodeUpdate) => void;
  onRequestSearch: () => void;
}

export default function BlockedCodesPanel({
  nodeId,
  excluded,
  onUpdate,
  onRequestSearch,
}: Props) {
  const terms = useBlockedTerms(excluded);

  return (
    <Box>
      <Stack direction="row" alignItems="baseline" spacing={0.75} sx={{ mb: 0.5 }}>
        <BlockIcon sx={{ fontSize: 14, color: "error.main", alignSelf: "center" }} />
        <Typography variant="caption" sx={{ fontWeight: 700, color: "text.primary" }}>
          Blocked codes
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {excluded.length} total
        </Typography>
      </Stack>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ display: "block", mb: 0.75, lineHeight: 1.45 }}
      >
        These codes will not fire the rule, even if they sit under a chip
        code.
      </Typography>
      <Stack
        direction="row"
        spacing={0.5}
        sx={{ mt: 0.5, flexWrap: "wrap", rowGap: 0.5 }}
      >
        {excluded.length === 0 ? (
          <Box
            sx={{
              width: "100%",
              py: 0.75,
              px: 1,
              borderRadius: 1,
              border: "1px dashed",
              borderColor: "divider",
              color: "text.secondary",
            }}
          >
            <Typography variant="caption">Nothing blocked yet.</Typography>
          </Box>
        ) : (
          excluded.map((cid) => (
            <BlockedCodeChip
              key={cid}
              conceptId={cid}
              term={terms[cid]}
              onRemove={() =>
                onUpdate({ kind: "remove_excluded", nodeId, conceptId: cid })
              }
            />
          ))
        )}
      </Stack>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        sx={{ mt: 1 }}
        alignItems={{ xs: "stretch", sm: "center" }}
      >
        <Button
          size="small"
          startIcon={<BlockIcon />}
          onClick={onRequestSearch}
          sx={{ textTransform: "none", fontWeight: 600 }}
        >
          Search a code to block
        </Button>
        <ManualBlockField
          onAdd={(cid) =>
            onUpdate({ kind: "add_excluded", nodeId, conceptId: cid })
          }
        />
      </Stack>
    </Box>
  );
}

function BlockedCodeChip({
  conceptId,
  term,
  onRemove,
}: {
  conceptId: string;
  /** Preferred term once resolved; undefined while loading, "" if unresolved. */
  term: string | undefined;
  onRemove: () => void;
}) {
  const friendly = term ? friendlyTerm(term) : "";
  const label = friendly || `code ${conceptId}`;
  return (
    <Tooltip title={`code ${conceptId}`} arrow>
      <Chip
        icon={<BlockIcon sx={{ fontSize: 12 }} />}
        label={label}
        size="small"
        variant="outlined"
        color="error"
        onDelete={onRemove}
        aria-label={`Unblock ${label}`}
        deleteIcon={<CloseIcon sx={{ fontSize: 13 }} />}
        sx={{
          height: 24,
          fontSize: "0.7rem",
          maxWidth: 240,
          bgcolor: "error.50",
          borderColor: "error.light",
          "& .MuiChip-icon": { color: "error.dark", ml: 0.5 },
          "& .MuiChip-label": { overflow: "hidden", textOverflow: "ellipsis" },
        }}
      />
    </Tooltip>
  );
}

/**
 * Resolves friendly terms for a set of bare SNOMED ids via the exact-id
 * match branch of ``/api/terminology/search``. Cached in component state
 * so an id is only looked up once per dialog session, even across
 * re-renders triggered by unrelated edits.
 */
function useBlockedTerms(ids: string[]): Record<string, string> {
  const [terms, setTerms] = useState<Record<string, string>>({});

  useEffect(() => {
    const missing = ids.filter((id) => terms[id] === undefined);
    if (missing.length === 0) return;
    let cancelled = false;

    Promise.all(missing.map(fetchTermForId)).then((resolved) => {
      if (cancelled) return;
      setTerms((prev) => {
        const next = { ...prev };
        for (const [id, term] of resolved) next[id] = term;
        return next;
      });
    });

    return () => {
      cancelled = true;
    };
    // `terms` is intentionally excluded: it is only read to compute
    // `missing` above, and including it would re-run this effect every
    // time a fetch resolves, looping forever.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ids.join(",")]);

  return terms;
}

function fetchTermForId(id: string): Promise<readonly [string, string]> {
  return fetch(`/api/terminology/search?q=${encodeURIComponent(id)}&limit=5`)
    .then((r) => (r.ok ? r.json() : []))
    .then((rows: ConceptSearchHit[]) => {
      const hit = Array.isArray(rows)
        ? rows.find((r) => r.snomed_concept_id === id)
        : undefined;
      return [id, hit?.term ?? ""] as const;
    })
    .catch(() => [id, ""] as const);
}

function ManualBlockField({ onAdd }: { onAdd: (conceptId: string) => void }) {
  const [value, setValue] = useState("");
  const trimmed = value.trim();
  const isNumeric = /^\d{4,18}$/.test(trimmed);
  return (
    <Stack direction="row" spacing={0.5} alignItems="center">
      <TextField
        size="small"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="paste SNOMED id"
        inputProps={{ "aria-label": "Block a SNOMED code by id" }}
        sx={{ width: 160 }}
      />
      <Button
        size="small"
        variant="outlined"
        disabled={!isNumeric}
        onClick={() => {
          onAdd(trimmed);
          setValue("");
        }}
      >
        Block
      </Button>
    </Stack>
  );
}
