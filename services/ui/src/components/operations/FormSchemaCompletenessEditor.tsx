/**
 * Completeness groups for a taught form: mandatory, optional, 1-of, n-of, if-then.
 *
 * Atlas trace: UN-3B25A20E
 */
"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import IconButton from "@mui/material/IconButton";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import { SnomedLookupField, type SnomedLookupValue } from "@/components/SnomedLookupField";

import {
  emptyCompletenessGroup,
  type CompletenessLogicGroup,
} from "./formSchemaTeach";

const KINDS = [
  { value: "mandatory", label: "Mandatory" },
  { value: "optional", label: "Optional" },
  { value: "one_of", label: "1 of these" },
  { value: "n_of", label: "At least N" },
  { value: "if_then", label: "If-then" },
] as const;

const EMPTY_LEAF: CompletenessLogicGroup = {
  name: "",
  kind: "optional",
  required: false,
  semantic_categories: [],
  concept_ids: [],
};

interface Props {
  groups: CompletenessLogicGroup[];
  onChange: (groups: CompletenessLogicGroup[]) => void;
}

function leafHasCodes(group: CompletenessLogicGroup | null | undefined): boolean {
  if (!group) return false;
  return Boolean(group.concept_ids?.length || group.semantic_categories?.length);
}

/** True when the evaluator cannot match this group to any extracted fact. */
export function hasNoCodes(group: CompletenessLogicGroup): boolean {
  const kind = group.kind || (group.required ? "mandatory" : "optional");
  if (kind === "one_of" || kind === "n_of") {
    const members = group.members ?? [];
    return !members.length || members.every((member) => !leafHasCodes(member));
  }
  if (kind === "if_then") {
    return !leafHasCodes(group.if_group) || !leafHasCodes(group.then_group);
  }
  return !leafHasCodes(group);
}

export function FormSchemaCompletenessEditor({ groups, onChange }: Props) {
  return (
    <Box sx={{ mt: 2 }} data-testid="form-completeness-editor">
      <Typography variant="subtitle2" fontWeight={700}>
        Completeness rules
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
        Say what this service must have. Search SNOMED so each rule can match facts.
      </Typography>
      <Stack spacing={1.25}>
        {groups.map((group, idx) => (
          <GroupRow
            key={`${group.name}-${idx}`}
            group={group}
            onChange={(next) => onChange(groups.map((item, i) => (i === idx ? next : item)))}
          />
        ))}
      </Stack>
      <Button
        size="small"
        startIcon={<AddIcon />}
        onClick={() => onChange([...groups, emptyCompletenessGroup()])}
        sx={{ mt: 1 }}
      >
        Add completeness rule
      </Button>
    </Box>
  );
}

function GroupRow({
  group,
  onChange,
}: {
  group: CompletenessLogicGroup;
  onChange: (group: CompletenessLogicGroup) => void;
}) {
  const kind = group.kind || (group.required ? "mandatory" : "optional");
  return (
    <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, p: 1 }}>
      <GroupHeader group={group} kind={kind} onChange={onChange} />
      {hasNoCodes(group) ? (
        <Alert severity="warning" sx={{ mt: 0.75, py: 0.25 }} data-testid="completeness-no-codes">
          No SNOMED code - this rule cannot match extracted facts. Search for a concept above.
        </Alert>
      ) : null}
      <GroupBody group={group} kind={kind} onChange={onChange} />
    </Box>
  );
}

function GroupHeader({
  group,
  kind,
  onChange,
}: {
  group: CompletenessLogicGroup;
  kind: string;
  onChange: (group: CompletenessLogicGroup) => void;
}) {
  return (
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
      <TextField
        size="small"
        label="Rule name"
        value={group.name}
        onChange={(e) => onChange({ ...group, name: e.target.value })}
        fullWidth
      />
      <TextField
        size="small"
        select
        label="Rule type"
        value={kind}
        onChange={(e) =>
          onChange({ ...group, kind: e.target.value, required: e.target.value !== "optional" })
        }
        sx={{ minWidth: 160 }}
      >
        {KINDS.map((item) => (
          <MenuItem key={item.value} value={item.value}>
            {item.label}
          </MenuItem>
        ))}
      </TextField>
      {kind === "n_of" ? (
        <TextField
          size="small"
          type="number"
          label="At least"
          value={group.min_count ?? 2}
          onChange={(e) => onChange({ ...group, min_count: Number(e.target.value) || 2 })}
          sx={{ width: 110 }}
          inputProps={{ min: 1, "aria-label": "At least N members" }}
        />
      ) : null}
    </Stack>
  );
}

function GroupBody({
  group,
  kind,
  onChange,
}: {
  group: CompletenessLogicGroup;
  kind: string;
  onChange: (group: CompletenessLogicGroup) => void;
}) {
  if (kind === "one_of" || kind === "n_of") {
    return (
      <MemberListEditor
        members={group.members ?? []}
        onChange={(members) => onChange({ ...group, members })}
      />
    );
  }
  if (kind === "if_then") {
    return <IfThenArms group={group} onChange={onChange} />;
  }
  return (
    <ConceptIdsEditor
      ids={group.concept_ids ?? []}
      onChange={(concept_ids) => onChange({ ...group, concept_ids })}
      testId="group-snomed"
    />
  );
}

function IfThenArms({
  group,
  onChange,
}: {
  group: CompletenessLogicGroup;
  onChange: (group: CompletenessLogicGroup) => void;
}) {
  return (
    <Stack spacing={1} sx={{ mt: 1 }}>
      <ArmEditor
        label="If this is present"
        arm={group.if_group ?? EMPTY_LEAF}
        onChange={(if_group) => onChange({ ...group, if_group })}
        testId="if-arm-snomed"
      />
      <ArmEditor
        label="Then also require"
        arm={group.then_group ?? EMPTY_LEAF}
        onChange={(then_group) => onChange({ ...group, then_group })}
        testId="then-arm-snomed"
      />
    </Stack>
  );
}

function ArmEditor({
  label,
  arm,
  onChange,
  testId,
}: {
  label: string;
  arm: CompletenessLogicGroup;
  onChange: (arm: CompletenessLogicGroup) => void;
  testId: string;
}) {
  return (
    <Stack spacing={1}>
      <TextField
        size="small"
        label={label}
        value={arm.name}
        onChange={(e) => onChange({ ...arm, name: e.target.value })}
        fullWidth
      />
      <ConceptIdsEditor
        ids={arm.concept_ids ?? []}
        onChange={(concept_ids) => onChange({ ...arm, concept_ids })}
        testId={testId}
      />
    </Stack>
  );
}

function MemberListEditor({
  members,
  onChange,
}: {
  members: CompletenessLogicGroup[];
  onChange: (members: CompletenessLogicGroup[]) => void;
}) {
  return (
    <Stack spacing={1} sx={{ mt: 1 }} data-testid="completeness-member-list">
      {members.map((member, idx) => (
        <Stack key={`${member.name}-${idx}`} spacing={0.75} direction={{ xs: "column", sm: "row" }}>
          <TextField
            size="small"
            label="Option name"
            value={member.name}
            onChange={(e) =>
              onChange(members.map((item, i) => (i === idx ? { ...item, name: e.target.value } : item)))
            }
            sx={{ minWidth: 160 }}
          />
          <ConceptIdsEditor
            ids={member.concept_ids ?? []}
            onChange={(concept_ids) =>
              onChange(members.map((item, i) => (i === idx ? { ...item, concept_ids } : item)))
            }
            testId={`member-snomed-${idx}`}
          />
          <IconButton
            aria-label={`Remove option ${member.name || idx + 1}`}
            onClick={() => onChange(members.filter((_, i) => i !== idx))}
            size="small"
          >
            <DeleteOutlineIcon fontSize="small" />
          </IconButton>
        </Stack>
      ))}
      <Button
        size="small"
        startIcon={<AddIcon />}
        onClick={() => onChange([...members, { ...EMPTY_LEAF, name: `Option ${members.length + 1}` }])}
      >
        Add option
      </Button>
    </Stack>
  );
}

function ConceptIdsEditor({
  ids,
  onChange,
  testId,
}: {
  ids: number[];
  onChange: (ids: number[]) => void;
  testId: string;
}) {
  const [adding, setAdding] = useState(false);
  const kept = ids.filter((cid) => cid > 0);
  const [first, ...extra] = kept;
  return (
    <Stack spacing={0.75} sx={{ mt: 1, flex: 1, minWidth: 0 }}>
      <SnomedLookupField
        label="SNOMED concept"
        ariaLabel="Search SNOMED for this completeness rule"
        semanticTags={[]}
        value={
          first
            ? { conceptId: String(first), display: String(first) }
            : { conceptId: "", display: "" }
        }
        onChange={(next) => applyFirstConcept(kept, next, onChange)}
        testId={testId}
      />
      {extra.map((cid) => (
        <SnomedLookupField
          key={cid}
          label="Also match"
          ariaLabel="Search another SNOMED concept for this rule"
          semanticTags={[]}
          value={{ conceptId: String(cid), display: String(cid) }}
          onChange={(next) => replaceOrDrop(kept, cid, next, onChange)}
          testId={`${testId}-extra-${cid}`}
        />
      ))}
      {adding ? (
        <SnomedLookupField
          label="Also match"
          ariaLabel="Search another SNOMED concept for this rule"
          semanticTags={[]}
          value={{ conceptId: "", display: "" }}
          onChange={(next) => {
            const parsed = Number(next.conceptId);
            if (!parsed) {
              setAdding(false);
              return;
            }
            onChange([...kept.filter((cid) => cid !== parsed), parsed]);
            setAdding(false);
          }}
          testId={`${testId}-add`}
        />
      ) : first ? (
        <Button size="small" startIcon={<AddIcon />} onClick={() => setAdding(true)}>
          Add another concept
        </Button>
      ) : null}
    </Stack>
  );
}

function applyFirstConcept(
  ids: number[],
  next: SnomedLookupValue,
  onChange: (ids: number[]) => void,
): void {
  const parsed = Number(next.conceptId);
  const rest = ids.slice(1).filter((cid) => cid > 0);
  if (!next.conceptId || !parsed) {
    onChange(rest);
    return;
  }
  onChange([parsed, ...rest.filter((cid) => cid !== parsed)]);
}

function replaceOrDrop(
  ids: number[],
  current: number,
  next: SnomedLookupValue,
  onChange: (ids: number[]) => void,
): void {
  const parsed = Number(next.conceptId);
  if (!next.conceptId || !parsed) {
    onChange(ids.filter((cid) => cid !== current));
    return;
  }
  onChange(ids.map((cid) => (cid === current ? parsed : cid)));
}
