/**
 * Atlas trace:
 *   DO: DO-CFA1ED55
 *   DI: DI-340279C1
 */
"use client";

import { useEffect, useState } from "react";
import Dialog from "@mui/material/Dialog";
import {
  frostStyle,
  useReducedTransparency,
} from "@leo/design-system";
import { color, elevation, radius } from "@leo/design-system/tokens";

import type { DomainSummary } from "@/lib/analyticsApi";
import { Field, ghostBtn, primaryBtn, titleStyle } from "./domainFormFields";

export function DomainFormDialogs({
  createOpen,
  editTarget,
  onCloseCreate,
  onCloseEdit,
  onCreate,
  onEdit,
}: {
  createOpen: boolean;
  editTarget: DomainSummary | null;
  onCloseCreate: () => void;
  onCloseEdit: () => void;
  onCreate: (name: string, description: string) => Promise<void>;
  onEdit: (id: string, name: string, description: string) => Promise<void>;
}) {
  return (
    <>
      <AreaFormDialog
        open={createOpen}
        title="Create a new area"
        submitLabel="Create"
        busyLabel="Creating..."
        onClose={onCloseCreate}
        onSubmit={onCreate}
      />
      <AreaFormDialog
        open={Boolean(editTarget)}
        title="Rename area"
        submitLabel="Save"
        busyLabel="Saving..."
        initialName={editTarget?.name ?? ""}
        initialDescription={editTarget?.description ?? ""}
        onClose={onCloseEdit}
        onSubmit={(name, description) =>
          editTarget ? onEdit(editTarget.id, name, description) : Promise.resolve()
        }
      />
    </>
  );
}

function AreaFormDialog({
  open,
  title,
  submitLabel,
  busyLabel,
  initialName = "",
  initialDescription = "",
  onClose,
  onSubmit,
}: {
  open: boolean;
  title: string;
  submitLabel: string;
  busyLabel: string;
  initialName?: string;
  initialDescription?: string;
  onClose: () => void;
  onSubmit: (name: string, description: string) => Promise<void>;
}) {
  const frost = frostStyle(useReducedTransparency(), "pane");
  const [name, setName] = useState(initialName);
  const [description, setDescription] = useState(initialDescription);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(initialName);
    setDescription(initialDescription);
    setError(null);
  }, [open, initialName, initialDescription]);

  return (
    <Dialog
      open={open}
      onClose={() => !busy && onClose()}
      maxWidth="sm"
      fullWidth
      PaperProps={{ style: { ...frost, boxShadow: elevation.modal, borderRadius: radius.lg } }}
    >
      <AreaForm
        title={title}
        name={name}
        description={description}
        error={error}
        busy={busy}
        submitLabel={submitLabel}
        busyLabel={busyLabel}
        onName={setName}
        onDescription={setDescription}
        onClose={onClose}
        onSubmit={() => void submitForm(name, description, setBusy, setError, onSubmit)}
      />
    </Dialog>
  );
}

function AreaForm({
  title,
  name,
  description,
  error,
  busy,
  submitLabel,
  busyLabel,
  onName,
  onDescription,
  onClose,
  onSubmit,
}: {
  title: string;
  name: string;
  description: string;
  error: string | null;
  busy: boolean;
  submitLabel: string;
  busyLabel: string;
  onName: (next: string) => void;
  onDescription: (next: string) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <form
      style={{ padding: 20, display: "grid", gap: 14 }}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <h2 style={titleStyle()}>{title}</h2>
      <Field id="area-name" label="Area name" value={name} onChange={onName} placeholder="e.g. Cardiology Audit" />
      <Field
        id="area-purpose"
        label="Description"
        value={description}
        onChange={onDescription}
        placeholder="Optional - what is this area for?"
        multiline
      />
      {error ? <p style={{ margin: 0, color: color.status.danger, fontSize: 13 }}>{error}</p> : null}
      <FormActions
        name={name}
        busy={busy}
        submitLabel={submitLabel}
        busyLabel={busyLabel}
        onClose={onClose}
      />
    </form>
  );
}

function FormActions({
  name,
  busy,
  submitLabel,
  busyLabel,
  onClose,
}: {
  name: string;
  busy: boolean;
  submitLabel: string;
  busyLabel: string;
  onClose: () => void;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
      <button type="button" onClick={onClose} disabled={busy} style={ghostBtn()}>
        Cancel
      </button>
      <button type="submit" disabled={!name.trim() || busy} style={primaryBtn(!name.trim() || busy)}>
        {busy ? busyLabel : submitLabel}
      </button>
    </div>
  );
}

async function submitForm(
  name: string,
  description: string,
  setBusy: (next: boolean) => void,
  setError: (next: string | null) => void,
  onSubmit: (name: string, description: string) => Promise<void>,
) {
  if (!name.trim()) return;
  setBusy(true);
  setError(null);
  try {
    await onSubmit(name.trim(), description.trim());
  } catch (e) {
    setError(e instanceof Error ? e.message : "Save failed. Please try again.");
  } finally {
    setBusy(false);
  }
}

