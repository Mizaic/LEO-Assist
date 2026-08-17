/**
 * DocumentListPanel -- split-pane clinical document browser.
 *
 * Left: collapsible specialty folders with chip filters.
 * Right: rendered letter / PDF link viewer (DocumentViewer).
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */
"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import AddIcon from "@mui/icons-material/Add";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import type { DocumentRow } from "@/lib/patientEprApi";
import { fetchEprAssessments, fetchEprDocuments } from "@/lib/patientEprApi";
import { DocumentViewer } from "./DocumentViewer";
import { DocumentEditorDialog } from "./DocumentEditorDialog";
import { DocumentFolderBlock } from "./DocumentFolderBlock";
import { JourneyBuilderPanel } from "./JourneyBuilderPanel";
import { useOrg } from "@/context/OrgContext";
import {
  documentFolderKey,
  folderCounts,
  matchesTypeFilter,
  sortFolderLabels,
  TYPE_FILTER_OPTIONS,
  type DocumentTypeFilter,
} from "./documentListFilters";
import { mergeDocumentsNewestFirst } from "./documentFormat";

const CONDITION_ACCENT: Record<string, string> = {
  lung: "#002178",
  breast: "#9D174D",
  prostate: "#6D28D9",
  colorectal: "#B45309",
  lower_gi: "#B45309",
  upper_gi: "#7C3AED",
  skin: "#047857",
  haematology: "#0369A1",
  gynaecology: "#BE185D",
  head_and_neck: "#0d46d6",
  urology: "#4338CA",
};

function accentForLabel(label: string): string {
  const key = label.toLowerCase().split(" ")[0].replace(/-/g, "_");
  return CONDITION_ACCENT[key] ?? "#475569";
}

function FilterChipRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <Stack spacing={0.5} sx={{ mb: 1 }}>
      <Typography variant="caption" fontWeight={700} color="text.secondary">
        {label}
      </Typography>
      <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
        {children}
      </Stack>
    </Stack>
  );
}

interface Props {
  patientId: string;
  scopeEpisodeIds?: string[];
  initialDocumentId?: string;
  initialReferralId?: string;
}

function docMatchesReferral(doc: DocumentRow, referralId: string): boolean {
  const prefix = referralId.trim();
  if (!prefix) return false;
  const docId = doc.document_id;
  return docId === prefix || docId.startsWith(`${prefix}-`);
}

export function DocumentListPanel({
  patientId,
  scopeEpisodeIds,
  initialDocumentId,
  initialReferralId,
}: Props) {
  const { isPlatformAdmin } = useOrg();
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<DocumentTypeFilter>("all");
  const [folderFilter, setFolderFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [expandedFolders, setExpandedFolders] = useState<Record<string, boolean>>({});

  const reloadDocs = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchEprDocuments(patientId),
      fetchEprAssessments(patientId).catch(() => []),
    ])
      .then(([rows, assessments]) => {
        const scopedDocs = scopeEpisodeIds
          ? rows.filter(
              (r) => !r.episode_id || scopeEpisodeIds.includes(r.episode_id),
            )
          : rows;
        const scopedAssessments = scopeEpisodeIds
          ? assessments.filter(
              (a) => !a.episode_id || scopeEpisodeIds.includes(a.episode_id),
            )
          : assessments;
        const merged = mergeDocumentsNewestFirst(scopedDocs, scopedAssessments);
        setDocs(merged);
        setSelectedId((prev) => {
          if (prev && merged.some((d) => d.document_id === prev)) return prev;
          return merged[0]?.document_id ?? null;
        });
        const labels = sortFolderLabels(Array.from(folderCounts(merged).keys()));
        setExpandedFolders((prev) => {
          const next: Record<string, boolean> = {};
          for (const label of labels) {
            next[label] = prev[label] ?? true;
          }
          return next;
        });
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Failed to load documents."),
      )
      .finally(() => setLoading(false));
  }, [patientId, scopeEpisodeIds]);

  useEffect(() => {
    reloadDocs();
  }, [reloadDocs]);

  useEffect(() => {
    if (loading || docs.length === 0) return;
    if (initialDocumentId && docs.some((d) => d.document_id === initialDocumentId)) {
      setSelectedId(initialDocumentId);
      return;
    }
    if (initialReferralId) {
      const match = docs.find((d) => docMatchesReferral(d, initialReferralId));
      if (match) setSelectedId(match.document_id);
    }
  }, [loading, docs, initialDocumentId, initialReferralId]);

  useEffect(() => {
    if (!selectedId) return;
    const selected = docs.find((d) => d.document_id === selectedId);
    if (!selected) return;
    const folder = documentFolderKey(selected);
    setExpandedFolders((prev) => ({ ...prev, [folder]: true }));
  }, [selectedId, docs]);

  const folderChipOptions = useMemo(() => {
    const counts = folderCounts(docs);
    return sortFolderLabels(Array.from(counts.keys())).map((label) => ({
      label,
      count: counts.get(label) ?? 0,
    }));
  }, [docs]);

  const filtered = useMemo(() => {
    let base = docs.filter((d) => matchesTypeFilter(d, typeFilter));
    if (folderFilter) {
      base = base.filter((d) => documentFolderKey(d) === folderFilter);
    }
    if (!search.trim()) return base;
    const q = search.toLowerCase();
    return base.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        (d.text_preview ?? "").toLowerCase().includes(q) ||
        (d.category ?? "").toLowerCase().includes(q) ||
        documentFolderKey(d).toLowerCase().includes(q),
    );
  }, [docs, typeFilter, folderFilter, search]);

  const grouped = useMemo(() => {
    const map = new Map<string, DocumentRow[]>();
    for (const doc of filtered) {
      const key = documentFolderKey(doc);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(doc);
    }
    return map;
  }, [filtered]);

  const sortedFolderEntries = useMemo(() => {
    return sortFolderLabels(Array.from(grouped.keys())).map((label) => [
      label,
      grouped.get(label) ?? [],
    ] as const);
  }, [grouped]);

  const selected = docs.find((d) => d.document_id === selectedId) ?? null;
  const allExpanded = sortedFolderEntries.every(([label]) => expandedFolders[label] !== false);
  const anyCollapsed = sortedFolderEntries.some(([label]) => expandedFolders[label] === false);

  const toggleFolder = (label: string) => {
    setExpandedFolders((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  const setAllFoldersExpanded = (expanded: boolean) => {
    setExpandedFolders((prev) => {
      const next = { ...prev };
      for (const [label] of sortedFolderEntries) {
        next[label] = expanded;
      }
      return next;
    });
  };

  if (loading) {
    return (
      <Stack spacing={1.5}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} variant="rounded" height={80} />
        ))}
      </Stack>
    );
  }

  if (error) return <Alert severity="error">{error}</Alert>;

  return (
    <Box>
      {isPlatformAdmin && (
        <JourneyBuilderPanel
          patientId={patientId}
          documents={docs}
          onDocumentsChanged={reloadDocs}
        />
      )}

      <Box sx={{ mb: 1.5 }}>
        <FilterChipRow label="Specialty">
          <Chip
            label="All specialties"
            size="small"
            onClick={() => setFolderFilter(null)}
            variant={folderFilter === null ? "filled" : "outlined"}
            color={folderFilter === null ? "primary" : "default"}
          />
          {folderChipOptions.map(({ label, count }) => (
            <Chip
              key={label}
              label={`${label} (${count})`}
              size="small"
              onClick={() => setFolderFilter(folderFilter === label ? null : label)}
              variant={folderFilter === label ? "filled" : "outlined"}
              color={folderFilter === label ? "primary" : "default"}
              sx={
                folderFilter === label
                  ? { bgcolor: accentForLabel(label), color: "#fff" }
                  : { borderColor: accentForLabel(label), color: accentForLabel(label) }
              }
            />
          ))}
        </FilterChipRow>

        <FilterChipRow label="Document type">
          {TYPE_FILTER_OPTIONS.map((opt) => (
            <Chip
              key={opt.id}
              label={opt.label}
              size="small"
              onClick={() => setTypeFilter(opt.id)}
              variant={typeFilter === opt.id ? "filled" : "outlined"}
              color={typeFilter === opt.id ? "primary" : "default"}
            />
          ))}
          {isPlatformAdmin && (
            <Button
              size="small"
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setEditorOpen(true)}
              data-testid="add-document-button"
              sx={{ ml: "auto" }}
            >
              Add document
            </Button>
          )}
        </FilterChipRow>
      </Box>

      <Box
        sx={{
          display: "flex",
          border: "1px solid #E2E8F0",
          borderRadius: "10px",
          overflow: "hidden",
          height: "calc(100vh - 340px)",
          minHeight: 420,
        }}
      >
        <Box
          sx={{
            width: 300,
            flexShrink: 0,
            borderRight: "1px solid #E2E8F0",
            display: "flex",
            flexDirection: "column",
            bgcolor: "#FFFFFF",
          }}
        >
          <Box sx={{ p: 1.25, borderBottom: "1px solid #E2E8F0" }}>
            <TextField
              size="small"
              placeholder="Search documents..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              fullWidth
              InputProps={{
                startAdornment: (
                  <DescriptionOutlinedIcon sx={{ mr: 0.5, fontSize: 16, color: "#94A3B8" }} />
                ),
              }}
            />
            {sortedFolderEntries.length > 1 && (
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button
                  size="small"
                  variant="text"
                  onClick={() => setAllFoldersExpanded(true)}
                  disabled={allExpanded}
                >
                  Expand all
                </Button>
                <Button
                  size="small"
                  variant="text"
                  onClick={() => setAllFoldersExpanded(false)}
                  disabled={anyCollapsed}
                >
                  Collapse all
                </Button>
              </Stack>
            )}
          </Box>
          <Box sx={{ flex: 1, overflowY: "auto" }}>
            {grouped.size === 0 ? (
              <Alert severity="info" sx={{ m: 1.25, fontSize: 12 }}>
                No documents match.
              </Alert>
            ) : (
              sortedFolderEntries.map(([label, labelDocs]) => (
                <DocumentFolderBlock
                  key={label}
                  label={label}
                  docs={labelDocs}
                  accent={accentForLabel(label)}
                  expanded={expandedFolders[label] !== false}
                  selectedId={selectedId}
                  onToggle={() => toggleFolder(label)}
                  onSelect={setSelectedId}
                />
              ))
            )}
          </Box>
        </Box>

        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: "#FFFFFF" }}>
          {selected ? (
            <DocumentViewer
              doc={selected}
              patientId={patientId}
              canManageDocuments={isPlatformAdmin}
              onDocumentsChanged={reloadDocs}
            />
          ) : (
            <Box sx={{ p: 4, textAlign: "center", color: "#94A3B8" }}>
              <ArticleOutlinedIcon sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="body2">Select a document to read it.</Typography>
            </Box>
          )}
        </Box>
      </Box>

      <DocumentEditorDialog
        open={editorOpen}
        patientId={patientId}
        onClose={() => setEditorOpen(false)}
        onSaved={() => reloadDocs()}
      />
    </Box>
  );
}
