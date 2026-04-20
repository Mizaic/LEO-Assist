/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

/**
 * SchemaBuilder — visual editor for the extraction output schema.
 *
 * Reads/writes a JSON Schema document that describes an object containing
 * a single array property ("terms") whose items are flat objects.
 *
 * Renders as:
 *   ┌─ Output is a list called "terms".  Each item has these fields: ──────┐
 *   │  field name │ type │ req │ nullable │ allowed values │ description   │
 *   │  ...rows... │      │     │          │                │               │
 *   │  [+ Add field]                                                       │
 *   └──────────────────────────────────────────────────────────────────────┘
 */

import { useEffect, useState, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import IconButton from "@mui/material/IconButton";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Checkbox from "@mui/material/Checkbox";
import Tooltip from "@mui/material/Tooltip";
import Alert from "@mui/material/Alert";
import Divider from "@mui/material/Divider";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import DragIndicatorIcon from "@mui/icons-material/DragIndicator";
import CodeIcon from "@mui/icons-material/Code";

// ── Types ─────────────────────────────────────────────────────────────────────

export type FieldType = "string" | "number" | "boolean" | "enum";

export interface SchemaField {
  id: string;
  name: string;
  type: FieldType;
  required: boolean;
  nullable: boolean;
  description: string;
  enumValues: string[];   // only used when type === "enum"
}

export interface OutputSchema {
  topLevelDescription: string;
  arrayName: string;         // e.g. "terms"
  fields: SchemaField[];
}

// ── JSON Schema serialiser / parser ──────────────────────────────────────────

function schemaToJson(schema: OutputSchema): object {
  const fieldProperties: Record<string, object> = {};
  const required: string[] = [];

  for (const f of schema.fields) {
    if (f.required) required.push(f.name);

    let typeDef: object;
    if (f.type === "enum") {
      typeDef = {
        type: f.nullable ? ["string", "null"] : "string",
        enum: f.nullable ? [...f.enumValues, null] : f.enumValues,
        description: f.description,
      };
    } else {
      typeDef = {
        type: f.nullable ? [f.type, "null"] : f.type,
        description: f.description,
      };
    }
    fieldProperties[f.name] = typeDef;
  }

  return {
    description: schema.topLevelDescription,
    type: "object",
    properties: {
      [schema.arrayName]: {
        type: "array",
        description: `One entry per extracted item.`,
        items: {
          type: "object",
          required,
          properties: fieldProperties,
        },
      },
    },
  };
}

function jsonToSchema(raw: string): OutputSchema | null {
  try {
    const parsed = JSON.parse(raw);
    const desc = parsed.description ?? "";
    const props = parsed.properties ?? {};
    const arrayName = Object.keys(props)[0] ?? "terms";
    const items = props[arrayName]?.items ?? {};
    const requiredFields: string[] = items.required ?? [];
    const itemProps: Record<string, any> = items.properties ?? {};

    const fields: SchemaField[] = Object.entries(itemProps).map(([name, def]: [string, any], idx) => {
      const rawType = def.type;
      const isNullable = Array.isArray(rawType)
        ? rawType.includes("null")
        : false;
      const baseType: string = Array.isArray(rawType)
        ? rawType.find((t: string) => t !== "null") ?? "string"
        : rawType ?? "string";
      const hasEnum = Array.isArray(def.enum);
      const enumValues: string[] = hasEnum
        ? (def.enum as any[]).filter((v) => v !== null).map(String)
        : [];

      return {
        id: `f_${idx}_${name}`,
        name,
        type: hasEnum ? "enum" : (baseType as FieldType),
        required: requiredFields.includes(name),
        nullable: isNullable,
        description: def.description ?? "",
        enumValues,
      };
    });

    return { topLevelDescription: desc, arrayName, fields };
  } catch {
    return null;
  }
}

// ── EnumValueEditor ───────────────────────────────────────────────────────────

function EnumValueEditor({
  values,
  onChange,
}: {
  values: string[];
  onChange: (v: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  };

  return (
    <Stack spacing={0.5}>
      <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
        {values.map((v) => (
          <Chip
            key={v} label={v} size="small"
            onDelete={() => onChange(values.filter((x) => x !== v))}
            sx={{ fontSize: "0.7rem", height: 20, fontFamily: "monospace" }}
          />
        ))}
      </Stack>
      <Stack direction="row" spacing={0.5}>
        <TextField
          size="small" placeholder="Add value…"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          sx={{ flex: 1, "& .MuiInputBase-input": { fontSize: "0.78rem", py: 0.5 } }}
        />
        <IconButton size="small" onClick={add} disabled={!draft.trim()}>
          <AddIcon fontSize="small" />
        </IconButton>
      </Stack>
    </Stack>
  );
}

// ── FieldRow ─────────────────────────────────────────────────────────────────

const TYPE_OPTIONS: { value: FieldType; label: string }[] = [
  { value: "string", label: "Text" },
  { value: "number", label: "Number" },
  { value: "boolean", label: "Yes/No" },
  { value: "enum", label: "Pick list" },
];

function FieldRow({
  field,
  isLast,
  onChange,
  onRemove,
}: {
  field: SchemaField;
  isLast: boolean;
  onChange: (f: SchemaField) => void;
  onRemove: () => void;
}) {
  const upd = (patch: Partial<SchemaField>) => onChange({ ...field, ...patch });

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "24px 150px 110px 44px 64px 1fr auto",
        columnGap: 1,
        alignItems: "flex-start",
        py: 1,
        borderBottom: isLast ? "none" : "1px solid",
        borderColor: "divider",
      }}
    >
      {/* drag handle (decorative) */}
      <Box sx={{ display: "flex", alignItems: "center", pt: 0.5 }}>
        <DragIndicatorIcon sx={{ fontSize: 16, color: "text.disabled" }} />
      </Box>

      {/* field name */}
      <TextField
        size="small" placeholder="field_name"
        value={field.name}
        onChange={(e) => upd({ name: e.target.value })}
        inputProps={{ style: { fontFamily: "monospace", fontSize: "0.82rem" } }}
        sx={{ "& .MuiInputBase-root": { height: 32 } }}
      />

      {/* type */}
      <Select
        size="small" value={field.type}
        onChange={(e) => upd({ type: e.target.value as FieldType, enumValues: [] })}
        sx={{ height: 32, fontSize: "0.82rem" }}
      >
        {TYPE_OPTIONS.map((o) => (
          <MenuItem key={o.value} value={o.value} sx={{ fontSize: "0.82rem" }}>
            {o.label}
          </MenuItem>
        ))}
      </Select>

      {/* required */}
      <Tooltip title="Required field?">
        <Checkbox size="small" checked={field.required}
          onChange={(e) => upd({ required: e.target.checked })}
          sx={{ p: 0.5, mt: 0.25 }} />
      </Tooltip>

      {/* nullable */}
      <Tooltip title="Can be null / empty?">
        <Checkbox size="small" checked={field.nullable}
          onChange={(e) => upd({ nullable: e.target.checked })}
          sx={{ p: 0.5, mt: 0.25 }} />
      </Tooltip>

      {/* description + enum values */}
      <Stack spacing={0.75}>
        <TextField
          size="small" placeholder="What is this field for?"
          value={field.description}
          onChange={(e) => upd({ description: e.target.value })}
          sx={{ "& .MuiInputBase-root": { height: 32, fontSize: "0.82rem" } }}
        />
        {field.type === "enum" && (
          <EnumValueEditor
            values={field.enumValues}
            onChange={(v) => upd({ enumValues: v })}
          />
        )}
      </Stack>

      {/* delete */}
      <IconButton size="small" onClick={onRemove} sx={{ mt: 0.25 }}>
        <DeleteIcon fontSize="small" />
      </IconButton>
    </Box>
  );
}

// ── SchemaBuilder ─────────────────────────────────────────────────────────────

interface SchemaBuilderProps {
  /** Raw JSON string from Neo4j */
  value: string;
  onChange: (json: string) => void;
}

export default function SchemaBuilder({ value, onChange }: SchemaBuilderProps) {
  const [schema, setSchema] = useState<OutputSchema | null>(null);
  const [parseError, setParseError] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  // Parse on mount / external change
  useEffect(() => {
    const parsed = jsonToSchema(value);
    if (parsed) {
      setSchema(parsed);
      setParseError(false);
    } else {
      setParseError(true);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const emit = useCallback(
    (next: OutputSchema) => {
      setSchema(next);
      onChange(JSON.stringify(schemaToJson(next), null, 2));
    },
    [onChange],
  );

  const updateField = useCallback(
    (id: string, updated: SchemaField) => {
      if (!schema) return;
      emit({ ...schema, fields: schema.fields.map((f) => (f.id === id ? updated : f)) });
    },
    [schema, emit],
  );

  const removeField = useCallback(
    (id: string) => {
      if (!schema) return;
      emit({ ...schema, fields: schema.fields.filter((f) => f.id !== id) });
    },
    [schema, emit],
  );

  const addField = useCallback(() => {
    if (!schema) return;
    const newField: SchemaField = {
      id: `f_new_${Date.now()}`,
      name: "",
      type: "string",
      required: false,
      nullable: true,
      description: "",
      enumValues: [],
    };
    emit({ ...schema, fields: [...schema.fields, newField] });
  }, [schema, emit]);

  if (parseError || !schema) {
    return (
      <Alert severity="warning" sx={{ mb: 1 }}>
        Could not parse this schema as a visual editor — showing raw JSON below. Fix the JSON to
        switch to the visual editor.
      </Alert>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
        <Box>
          <Typography variant="subtitle2" fontWeight={700}>
            Output structure
          </Typography>
          <Typography variant="caption" color="text.secondary">
            This prompt returns a list called{" "}
            <Box component="code" sx={{ fontFamily: "monospace", bgcolor: "grey.100", px: 0.5, borderRadius: 0.5 }}>
              {schema.arrayName}
            </Box>
            . Each item has the fields below.
          </Typography>
        </Box>
        <Tooltip title={showRaw ? "Switch to visual editor" : "Show raw JSON"}>
          <Button size="small" variant="outlined" startIcon={<CodeIcon fontSize="small" />}
            onClick={() => setShowRaw((v) => !v)}>
            {showRaw ? "Visual" : "JSON"}
          </Button>
        </Tooltip>
      </Stack>

      {showRaw ? (
        <TextField
          fullWidth multiline minRows={12} size="small"
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            const parsed = jsonToSchema(e.target.value);
            if (parsed) { setSchema(parsed); setParseError(false); }
            else setParseError(true);
          }}
          inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem" } }}
        />
      ) : (
        <Paper variant="outlined" sx={{ borderRadius: 2, overflow: "hidden" }}>
          {/* Column headers */}
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "24px 150px 110px 44px 64px 1fr auto",
              columnGap: 1,
              px: 1.5,
              py: 0.75,
              bgcolor: "grey.50",
              borderBottom: "1px solid",
              borderColor: "divider",
            }}
          >
            {["", "Field name", "Type", "Req.", "Nullable", "Description / Allowed values", ""].map((h, i) => (
              <Typography key={i} variant="caption" fontWeight={700} color="text.secondary">
                {h}
              </Typography>
            ))}
          </Box>

          {/* Field rows */}
          <Box sx={{ px: 1.5 }}>
            {schema.fields.length === 0 ? (
              <Box sx={{ py: 3, textAlign: "center" }}>
                <Typography variant="body2" color="text.secondary">
                  No fields yet — add one below.
                </Typography>
              </Box>
            ) : (
              schema.fields.map((f, idx) => (
                <FieldRow
                  key={f.id}
                  field={f}
                  isLast={idx === schema.fields.length - 1}
                  onChange={(updated) => updateField(f.id, updated)}
                  onRemove={() => removeField(f.id)}
                />
              ))
            )}
          </Box>

          <Divider />
          <Box sx={{ px: 1.5, py: 1 }}>
            <Button size="small" startIcon={<AddIcon />} onClick={addField}>
              Add field
            </Button>
          </Box>
        </Paper>
      )}

      {/* Instruction note */}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
        At runtime the AI receives this as a structured prompt section — it does not see the raw JSON Schema,
        only the rendered instructions and example output.
      </Typography>
    </Box>
  );
}
