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

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Skeleton from "@mui/material/Skeleton";
import Stack from "@mui/material/Stack";
import { EmptyState, color, radius } from "@leo/design-system";
import ArticleOutlinedIcon from "@mui/icons-material/ArticleOutlined";
import type { DocumentRow } from "@/lib/patientEprApi";
import { fetchEprAssessments, fetchEprDocuments } from "@/lib/patientEprApi";
import { DocumentViewer } from "./DocumentViewer";
import { DocumentEditorDialog } from "./DocumentEditorDialog";
import { DocumentFolderBlock } from "./DocumentFolderBlock";
import { DocumentWorkspaceToolbar } from "./DocumentWorkspaceToolbar";
import { JourneyBuilderPanel } from "./JourneyBuilderPanel";
import { useOrg } from "@/context/OrgContext";
import {
  documentFolderKey,
  folderCounts,
  matchesTypeFilter,
  sortFolderLabels,
  type DocumentTypeFilter,
} from "./documentListFilters";
import { mergeDocumentsNewestFirst } from "./documentFormat";
import { accentFor } from "./episodeAccent";

function accentForLabel(label: string): string {
  return accentFor(label.toLowerCase().split(" ")[0] ?? null);
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

  const reloadDocs = useCallback((preferredId?: string) => {
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
          if (preferredId && merged.some((d) => d.document_id === preferredId)) {
            return preferredId;
          }
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
    <Box
      data-testid="epr-document-workspace"
      sx={{
        height: "100%",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        gap: 1.5,
      }}
    >
      <DocumentWorkspaceToolbar
        search={search}
        onSearchChange={setSearch}
        typeFilter={typeFilter}
        onTypeFilter={setTypeFilter}
        folderFilter={folderFilter}
        onFolderFilter={setFolderFilter}
        folderOptions={folderChipOptions}
        canAdd={isPlatformAdmin}
        onAdd={() => setEditorOpen(true)}
      />

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          border: "1px solid",
          borderColor: "divider",
          borderRadius: `${radius.md}px`,
          overflow: "hidden",
          bgcolor: color.surface.raised,
        }}
      >
        <Box
          sx={{
            width: { xs: 220, sm: 280 },
            flexShrink: 0,
            borderRight: "1px solid",
            borderColor: "divider",
            display: "flex",
            flexDirection: "column",
            bgcolor: color.surface.alt,
          }}
        >
          {sortedFolderEntries.length > 1 && (
            <Stack
              direction="row"
              spacing={1}
              sx={{ px: 1.25, py: 1, borderBottom: "1px solid", borderColor: "divider" }}
            >
              <Button
                size="small"
                variant="text"
                onClick={() => setAllFoldersExpanded(true)}
                disabled={allExpanded}
                sx={{ textTransform: "none" }}
              >
                Expand all
              </Button>
              <Button
                size="small"
                variant="text"
                onClick={() => setAllFoldersExpanded(false)}
                disabled={anyCollapsed}
                sx={{ textTransform: "none" }}
              >
                Collapse all
              </Button>
            </Stack>
          )}
          <Box sx={{ flex: 1, overflowY: "auto" }}>
            {grouped.size === 0 ? (
              <Alert severity="info" sx={{ m: 1.25 }}>
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

        <Box sx={{ flex: 1, overflowY: "auto", bgcolor: color.surface.raised }}>
          {selected ? (
            <DocumentViewer
              doc={selected}
              patientId={patientId}
              canManageDocuments={isPlatformAdmin}
              onDocumentsChanged={reloadDocs}
            />
          ) : (
            <EmptyState
              icon={<ArticleOutlinedIcon />}
              title="Select a document"
              body="Pick a letter or summary from the list to read it here."
            />
          )}
        </Box>
      </Box>

      {isPlatformAdmin && (
        <JourneyBuilderPanel
          patientId={patientId}
          documents={docs}
          onDocumentsChanged={reloadDocs}
        />
      )}

      <DocumentEditorDialog
        open={editorOpen}
        patientId={patientId}
        onClose={() => setEditorOpen(false)}
        onSaved={() => reloadDocs()}
      />
    </Box>
  );
}
