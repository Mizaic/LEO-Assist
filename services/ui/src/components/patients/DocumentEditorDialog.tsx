/**
 * Create or edit a manual journey document.
 *
 * Atlas trace:
 *   DI: DI-DD1989E6
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import type { MarkdownEditorHandle } from "@/components/markdown-editor";
import MarkdownEditor from "@/components/markdown-editor";
import {
  createPatientDocument,
  JOURNEY_MILESTONES,
  updatePatientDocument,
  type PatientDocumentResult,
} from "@/lib/patientDocumentsApi";

export interface DocumentEditorInitial {
  documentId?: string;
  title?: string;
  category?: string;
  documentDate?: string;
  markdownBody?: string;
  episodeId?: string;
  milestoneType?: string;
}

interface Props {
  open: boolean;
  patientId: string;
  initial?: DocumentEditorInitial;
  onClose: () => void;
  onSaved: (result: PatientDocumentResult) => void;
}

const CATEGORY_OPTIONS = [
  { id: "referral", label: "Referral" },
  { id: "letter", label: "Letter" },
  { id: "summary", label: "Summary" },
];

export function DocumentEditorDialog({
  open,
  patientId,
  initial,
  onClose,
  onSaved,
}: Props) {
  const editorRef = useRef<MarkdownEditorHandle>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState(initial?.title ?? "");
  const [category, setCategory] = useState(initial?.category ?? "referral");
  const [documentDate, setDocumentDate] = useState(initial?.documentDate ?? "");
  const [episodeId, setEpisodeId] = useState(initial?.episodeId ?? "");
  const [milestoneType, setMilestoneType] = useState(initial?.milestoneType ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const isEdit = Boolean(initial?.documentId);

  useEffect(() => {
    if (!open) return;
    setTitle(initial?.title ?? "");
    setCategory(initial?.category ?? "referral");
    setDocumentDate(initial?.documentDate ?? "");
    setEpisodeId(initial?.episodeId ?? "");
    setMilestoneType(initial?.milestoneType ?? "");
    setError(null);
    editorRef.current?.setMarkdown(initial?.markdownBody ?? "");
  }, [open, initial]);

  const handleUpload = async (file: File) => {
    const text = await file.text();
    editorRef.current?.setMarkdown(text);
  };

  const handleSave = async () => {
    setError(null);
    const markdownBody = editorRef.current?.getMarkdown()?.trim() ?? "";
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    if (!markdownBody) {
      setError("Document content is required.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        markdown_body: markdownBody,
        category,
        document_date: documentDate,
        episode_id: episodeId,
        milestone_type: milestoneType,
      };
      const result = isEdit
        ? await updatePatientDocument(patientId, initial!.documentId!, payload)
        : await createPatientDocument(patientId, payload);
      onSaved(result);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save document.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{isEdit ? "Edit document" : "Add document"}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            required
          />
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              select
              label="Category"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              fullWidth
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <MenuItem key={opt.id} value={opt.id}>
                  {opt.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Document date"
              type="date"
              value={documentDate}
              onChange={(e) => setDocumentDate(e.target.value)}
              InputLabelProps={{ shrink: true }}
              fullWidth
            />
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              label="Episode id"
              value={episodeId}
              onChange={(e) => setEpisodeId(e.target.value)}
              fullWidth
              helperText="Optional. Links this document to a journey episode."
            />
            <TextField
              select
              label="Milestone"
              value={milestoneType}
              onChange={(e) => setMilestoneType(e.target.value)}
              fullWidth
            >
              <MenuItem value="">None</MenuItem>
              {JOURNEY_MILESTONES.map((m) => (
                <MenuItem key={m.id} value={m.id}>
                  {m.label}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction="row" spacing={1}>
            <Button
              variant="outlined"
              startIcon={<UploadFileOutlinedIcon />}
              onClick={() => fileInputRef.current?.click()}
            >
              Upload .txt
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,text/plain"
              hidden
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleUpload(file);
                e.target.value = "";
              }}
            />
          </Stack>
          <MarkdownEditor
            ref={editorRef}
            initialContent={initial?.markdownBody ?? ""}
            mode="edit"
            placeholder="Paste markdown or plain text here..."
            minHeight={260}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button variant="contained" onClick={() => void handleSave()} disabled={saving}>
          {saving ? "Saving..." : isEdit ? "Save changes" : "Add document"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
