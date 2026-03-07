"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Switch from "@mui/material/Switch";
import FormControlLabel from "@mui/material/FormControlLabel";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import InputLabel from "@mui/material/InputLabel";
import FormControl from "@mui/material/FormControl";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SaveIcon from "@mui/icons-material/Save";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import FilterListIcon from "@mui/icons-material/FilterList";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import EditIcon from "@mui/icons-material/Edit";
import VisibilityIcon from "@mui/icons-material/Visibility";
import MarkdownEditor from "@/components/markdown-editor";
import type { MarkdownEditorHandle } from "@/components/markdown-editor";
import SchemaBuilder from "@/components/schema-builder/SchemaBuilder";
import { api } from "@/lib/api";

interface FewShotExample {
  id: string;
  input: string;
  output: string;
  deidentified: boolean;
  category: string;
  model_scope: string;
  description: string;
}

interface PromptConfigData {
  id: string;
  name: string;
  description: string;
  version: number;
  systemPrompt: string;
  outputSchema: string;
  verification: boolean;
  fewShotExamples: FewShotExample[];
}

// ── Category taxonomy for example library ────────────────────────────────────
const CATEGORY_OPTIONS = [
  { value: "", label: "All categories" },
  { value: "assertion:absent", label: "Absent / negated" },
  { value: "assertion:possible", label: "Possible / uncertain" },
  { value: "assertion:historical", label: "Historical / resolved" },
  { value: "assertion:hypothetical", label: "Hypothetical / planned" },
  { value: "assertion:family", label: "Family history" },
  { value: "assertion:refuted", label: "Refuted (overridden)" },
  { value: "assertion:declined", label: "Declined by patient" },
  { value: "assertion:cancelled", label: "Cancelled" },
  { value: "negation:compound", label: "Compound negation" },
  { value: "multi-entity", label: "Multiple entities" },
  { value: "observable", label: "Observable / lab result" },
  { value: "vital-signs", label: "Vital signs" },
  { value: "staging", label: "Cancer staging / performance status" },
  { value: "abbreviation", label: "Abbreviation expansion" },
  { value: "brand-name", label: "Brand name → generic" },
  { value: "situation:allergy", label: "Allergy status" },
  { value: "situation:referral", label: "Referral / planned procedure" },
  { value: "situation:smoking", label: "Smoking status" },
];

const SCOPE_OPTIONS = [
  { value: "any",   label: "Both providers (AWS + Azure)" },
  { value: "aws",   label: "AWS only (Claude / Bedrock)" },
  { value: "azure", label: "Azure only (OpenAI / GPT)" },
];

function categoryLabel(cat: string) {
  return CATEGORY_OPTIONS.find((o) => o.value === cat)?.label ?? cat;
}

function categoryColor(cat: string): "default" | "primary" | "secondary" | "error" | "warning" | "info" | "success" {
  if (cat.startsWith("assertion:absent") || cat.startsWith("negation")) return "error";
  if (cat.startsWith("assertion:possible")) return "warning";
  if (cat.startsWith("assertion:historical")) return "secondary";
  if (cat.startsWith("assertion:declined") || cat.startsWith("assertion:cancelled")) return "error";
  if (cat.startsWith("assertion:family")) return "info";
  if (cat.startsWith("staging")) return "secondary";
  if (cat.startsWith("observable") || cat.startsWith("vital")) return "primary";
  if (cat.startsWith("multi")) return "warning";
  return "default";
}

// ── Semantic tag / assertion colour maps ──────────────────────────────────────
const TAG_COLORS: Record<string, "default" | "primary" | "secondary" | "error" | "warning" | "info" | "success"> = {
  disorder:          "error",
  finding:           "warning",
  "observable entity": "primary",
  procedure:         "info",
  substance:         "secondary",
  product:           "secondary",
  situation:         "default",
  "regime/therapy":  "info",
  "staging scale":   "success",
};

const ASSERTION_COLORS: Record<string, "default" | "primary" | "secondary" | "error" | "warning" | "info" | "success"> = {
  present:     "success",
  absent:      "error",
  refuted:     "error",
  possible:    "warning",
  historical:  "default",
  hypothetical:"info",
  family:      "info",
  declined:    "warning",
  cancelled:   "default",
};

// ── Human-readable input display ──────────────────────────────────────────────
function InputDisplay({ text }: { text: string }) {
  if (!text.trim()) {
    return <Typography variant="body2" color="text.disabled" fontStyle="italic">No input text yet</Typography>;
  }
  // Split on sentence markers like [s0], [s1] …
  const segments = text.split(/(?=\[s\d+\])/g).filter(Boolean);
  return (
    <Stack spacing={0.5}>
      {segments.map((seg, i) => {
        const m = seg.match(/^\[s(\d+)\]\s*([\s\S]*)/);
        if (m) {
          return (
            <Stack key={i} direction="row" spacing={0.75} alignItems="flex-start">
              <Chip size="small" label={`s${m[1]}`} variant="outlined"
                sx={{ height: 18, fontSize: "0.62rem", fontFamily: "monospace", flexShrink: 0, mt: "3px" }} />
              <Typography variant="body2">{m[2]}</Typography>
            </Stack>
          );
        }
        return <Typography key={i} variant="body2">{seg}</Typography>;
      })}
    </Stack>
  );
}

// ── Visual output preview ─────────────────────────────────────────────────────
function OutputPreview({ outputJson }: { outputJson: string }) {
  if (!outputJson.trim()) {
    return <Typography variant="body2" color="text.disabled" fontStyle="italic">No expected output yet</Typography>;
  }
  let terms: Record<string, string | null>[] = [];
  let parseError = false;
  try {
    const data = JSON.parse(outputJson);
    terms = Array.isArray(data.terms) ? data.terms : [];
  } catch {
    parseError = true;
  }

  if (parseError) {
    return (
      <Alert severity="error" sx={{ py: 0.25, fontSize: "0.75rem" }}>
        Output JSON is invalid — switch to Edit to fix it.
      </Alert>
    );
  }

  if (terms.length === 0) {
    return (
      <Box sx={{ px: 1.5, py: 1, bgcolor: "grey.50", borderRadius: 1,
        border: "1px dashed", borderColor: "divider", display: "inline-flex", alignItems: "center" }}>
        <Typography variant="caption" color="text.secondary">
          No entities extracted — correct for pure administrative text
        </Typography>
      </Box>
    );
  }

  return (
    <Stack spacing={0.5}>
      {terms.map((t, i) => (
        <Stack key={i} direction="row" alignItems="center" spacing={0.5} flexWrap="wrap" useFlexGap
          sx={{ p: 0.75, bgcolor: "grey.50", borderRadius: 1 }}>
          <Typography variant="body2" fontWeight={700} sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
            &ldquo;{t.text}&rdquo;
          </Typography>
          {t.lookup_term && t.lookup_term !== t.text && (
            <>
              <Typography variant="caption" color="text.disabled" sx={{ mx: 0.25 }}>→</Typography>
              <Typography variant="caption" color="text.secondary" fontStyle="italic">{t.lookup_term}</Typography>
            </>
          )}
          <Chip size="small" label={t.semantic_tag ?? "?"}
            color={TAG_COLORS[t.semantic_tag ?? ""] ?? "default"}
            sx={{ height: 18, fontSize: "0.62rem" }} />
          <Chip size="small" label={t.assertion ?? "?"}
            color={ASSERTION_COLORS[t.assertion ?? ""] ?? "default"}
            variant="outlined"
            sx={{ height: 18, fontSize: "0.62rem" }} />
          {(t.value || t.unit) && (
            <Chip size="small"
              label={[t.value, t.unit].filter(Boolean).join(" ")}
              sx={{ height: 18, fontSize: "0.62rem", bgcolor: "primary.50", color: "primary.dark" }} />
          )}
          {t.reference_range && (
            <Chip size="small" label={`range: ${t.reference_range}`} variant="outlined"
              sx={{ height: 18, fontSize: "0.62rem" }} />
          )}
        </Stack>
      ))}
    </Stack>
  );
}

// ── Example card ──────────────────────────────────────────────────────────────
function ExampleCard({
  ex, idx, onChange, onRemove, startInEdit = false,
}: {
  ex: FewShotExample;
  idx: number;
  onChange: (id: string, field: keyof FewShotExample, value: string | boolean) => void;
  onRemove: (id: string) => void;
  startInEdit?: boolean;
}) {
  const [editing, setEditing] = useState(startInEdit);

  return (
    <Card variant="outlined" sx={{ mb: 1.5, borderRadius: 2 }}>
      <CardContent sx={{ pb: "12px !important" }}>

        {/* ── Header row ── */}
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 1.25 }}>
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="caption" fontWeight={700} color="text.secondary">#{idx + 1}</Typography>
            {ex.category && (
              <Chip size="small" label={categoryLabel(ex.category)} color={categoryColor(ex.category)}
                sx={{ height: 18, fontSize: "0.65rem" }} />
            )}
            {ex.description && (
              <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
                {ex.description}
              </Typography>
            )}
          </Stack>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            {!ex.deidentified && ex.input && (
              <Chip size="small" label="Check for patient data" color="warning"
                sx={{ height: 18, fontSize: "0.62rem" }} />
            )}
            <Tooltip title={editing ? "Show preview" : "Edit this example"}>
              <IconButton size="small" onClick={() => setEditing((v) => !v)}>
                {editing ? <VisibilityIcon fontSize="small" /> : <EditIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
            <IconButton size="small" onClick={() => onRemove(ex.id)}>
              <DeleteIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Stack>

        {editing ? (
          /* ── Edit mode ── */
          <Stack spacing={1.25}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField size="small" label="What does this example show?" placeholder="e.g. Simple negation of a finding"
                value={ex.description} sx={{ flex: 2 }}
                onChange={(e) => onChange(ex.id, "description", e.target.value)} />
              <FormControl size="small" sx={{ flex: 1, minWidth: 170 }}>
                <InputLabel>Category</InputLabel>
                <Select label="Category" value={ex.category}
                  onChange={(e) => onChange(ex.id, "category", e.target.value)}>
                  {CATEGORY_OPTIONS.filter((o) => o.value).map((o) => (
                    <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ flex: 1, minWidth: 150 }}>
                <InputLabel>Provider</InputLabel>
                <Select label="Provider" value={ex.model_scope || "any"}
                  onChange={(e) => onChange(ex.id, "model_scope", e.target.value)}>
                  {SCOPE_OPTIONS.map((o) => (
                    <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Stack>

            <TextField fullWidth size="small" label="Clinical text the AI sees"
              placeholder='[s0] No fever.'
              multiline minRows={1} value={ex.input}
              onChange={(e) => onChange(ex.id, "input", e.target.value)}
              helperText='Start each sentence with [s0], [s1], etc.' />

            <TextField fullWidth size="small" label='Expected output JSON'
              placeholder='{"terms": [...]}'
              multiline minRows={3} value={ex.output}
              onChange={(e) => onChange(ex.id, "output", e.target.value)}
              inputProps={{ style: { fontFamily: "monospace", fontSize: "0.78rem" } }} />

            <FormControlLabel
              control={
                <Switch size="small" checked={ex.deidentified}
                  onChange={(e) => onChange(ex.id, "deidentified", e.target.checked)} color="success" />
              }
              label={
                <Typography variant="caption" color={ex.deidentified ? "success.main" : "text.secondary"}>
                  {ex.deidentified ? "Confirmed: no patient-identifiable data" : "Mark as de-identified when you've checked for names/numbers"}
                </Typography>
              }
              sx={{ m: 0 }}
            />
          </Stack>
        ) : (
          /* ── Preview mode ── */
          <Stack spacing={1.25}>
            <Box>
              <Typography variant="caption" color="text.disabled" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>
                CLINICAL TEXT
              </Typography>
              <InputDisplay text={ex.input} />
            </Box>
            <Divider />
            <Box>
              <Typography variant="caption" color="text.disabled" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>
                EXPECTED OUTPUT
              </Typography>
              <OutputPreview outputJson={ex.output} />
            </Box>
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function PromptTunerPage() {
  const params   = useParams();
  const router   = useRouter();
  const promptId = params.id as string;
  const isNew    = promptId === "new";

  const editorRef = useRef<MarkdownEditorHandle>(null);

  const [tab,             setTab]             = useState(0);
  const [name,            setName]            = useState("");
  const [description,     setDescription]     = useState("");
  const [systemPrompt,    setSystemPrompt]    = useState("");
  const [outputSchema,    setOutputSchema]    = useState("{}");
  const [verification,    setVerification]    = useState(false);
  const [fewShotExamples, setFewShotExamples] = useState<FewShotExample[]>([]);
  const [aiSuggestion,    setAiSuggestion]    = useState<string | null>(null);
  const [improving,       setImproving]       = useState(false);
  const [saving,          setSaving]          = useState(false);
  const [version,         setVersion]         = useState<number | null>(null);
  const [loaded,          setLoaded]          = useState(false);

  // Example library filters
  const [filterCat,   setFilterCat]   = useState("");
  const [filterScope, setFilterScope] = useState("");

  useEffect(() => {
    if (!isNew) {
      api.get<PromptConfigData>(`/api/prompts/${promptId}`)
        .then((data) => {
          setName(data.name);
          setDescription(data.description || "");
          setSystemPrompt(data.systemPrompt);
          setOutputSchema(data.outputSchema || "{}");
          setVerification(data.verification);
          setFewShotExamples(
            (data.fewShotExamples || []).map((ex) => ({
              ...ex,
              category:    ex.category    ?? "",
              model_scope: ex.model_scope ?? "any",
              description: ex.description ?? "",
            }))
          );
          setVersion(data.version);
          setLoaded(true);
        })
        .catch(() => setLoaded(true));
    } else {
      setLoaded(true);
    }
  }, [promptId, isNew]);

  useEffect(() => {
    if (loaded && systemPrompt) editorRef.current?.setMarkdown(systemPrompt);
  }, [loaded]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleEditorChange = useCallback((md: string) => setSystemPrompt(md), []);

  const handleAiImprove = useCallback(async () => {
    setImproving(true);
    try {
      const result = await api.post<{ improvedPrompt: string }>("/api/prompts/improve", {
        currentPrompt: systemPrompt,
        outputSchema,
      });
      setAiSuggestion(result.improvedPrompt);
    } catch {
      setAiSuggestion(null);
    } finally {
      setImproving(false);
    }
  }, [systemPrompt, outputSchema]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    const payload = {
      name,
      description,
      systemPrompt: editorRef.current?.getMarkdown() ?? systemPrompt,
      outputSchema,
      verification,
      fewShotExamples,
    };
    try {
      if (isNew) {
        const result = await api.post<{ id: string }>("/api/prompts", payload);
        router.push(`/admin/prompts/${result.id}`);
      } else {
        await api.put(`/api/prompts/${promptId}`, payload);
      }
    } catch {} finally {
      setSaving(false);
    }
  }, [name, description, systemPrompt, outputSchema, verification, fewShotExamples, isNew, promptId, router]);

  const addExample = useCallback(() => {
    setFewShotExamples((prev) => [
      ...prev,
      {
        id: `ex_${Date.now()}`,
        input: "", output: "",
        deidentified: false,
        category: "",
        model_scope: "any",
        description: "",
      },
    ]);
  }, []);

  const removeExample = useCallback((id: string) => {
    setFewShotExamples((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const updateExample = useCallback(
    (id: string, field: keyof FewShotExample, value: string | boolean) => {
      setFewShotExamples((prev) => prev.map((e) => (e.id === id ? { ...e, [field]: value } : e)));
    },
    [],
  );

  const filteredExamples = fewShotExamples.filter((ex) => {
    if (filterCat && ex.category !== filterCat) return false;
    if (filterScope && ex.model_scope !== filterScope) return false;
    return true;
  });

  // Count examples by category for badges
  const catCounts = fewShotExamples.reduce<Record<string, number>>((acc, ex) => {
    const k = ex.category || "uncategorised";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <Box sx={{ p: 3, maxWidth: 920, mx: "auto" }}>
      {/* Header */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
        <IconButton onClick={() => router.push("/admin/prompts")} aria-label="Back">
          <ArrowBackIcon />
        </IconButton>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" fontWeight={700}>
            {isNew ? "New AI instructions" : "Edit AI instructions"}
          </Typography>
          {!isNew && version !== null && (
            <Typography variant="caption" color="text.secondary">v{version}</Typography>
          )}
        </Box>
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />}
          onClick={handleSave}
          disabled={saving || !name}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
      </Stack>

      {/* Name + description */}
      <Paper variant="outlined" sx={{ p: 2.5, mb: 2, borderRadius: 2 }}>
        <Stack spacing={1.5}>
          <TextField fullWidth size="small" label="Name"
            placeholder="e.g. Standard clinical coder, Referral letter extractor"
            value={name} onChange={(e) => setName(e.target.value)} />
          <TextField fullWidth size="small" label="What is this for?" multiline rows={2}
            placeholder="A plain English summary of what these instructions do — shown on the cards page."
            value={description} onChange={(e) => setDescription(e.target.value)} />
          <FormControlLabel
            control={<Switch checked={verification}
              onChange={(e) => setVerification(e.target.checked)} color="success" size="small" />}
            label={
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <Typography variant="body2">Double-check results</Typography>
                <Tooltip title="When on, a second AI check runs after the first to confirm accuracy before saving.">
                  <InfoOutlinedIcon sx={{ fontSize: 15, color: "text.disabled" }} />
                </Tooltip>
                {verification && (
                  <Chip size="small" label="On" color="success"
                    icon={<CheckCircleOutlineIcon sx={{ fontSize: "13px !important" }} />} />
                )}
              </Stack>
            }
          />
        </Stack>
      </Paper>

      {/* Tabs */}
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 0, borderBottom: "1px solid", borderColor: "divider" }}>
        <Tab label="Instructions" />
        <Tab label="Output format" />
        <Tab
          label={
            <Stack direction="row" alignItems="center" spacing={0.75}>
              <span>Teaching examples</span>
              <Chip size="small" label={fewShotExamples.length}
                sx={{ height: 18, fontSize: "0.68rem",
                  bgcolor: fewShotExamples.length > 0 ? "primary.100" : "grey.200",
                  color: fewShotExamples.length > 0 ? "primary.main" : "text.disabled" }} />
            </Stack>
          }
        />
      </Tabs>

      {/* ── Tab 0: Instructions ─────────────────────────────────────────── */}
      {tab === 0 && (
        <Box sx={{ pt: 2 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Write the rules the AI follows — scope, semantic tags, assertion logic. Do not include
              examples or output format here; manage those in the other tabs.
            </Typography>
            <Tooltip title="Use the AI assistant to review and improve these instructions.">
              <Button size="small" variant="outlined"
                startIcon={improving ? <CircularProgress size={14} /> : <AutoFixHighIcon />}
                onClick={handleAiImprove} disabled={improving || !systemPrompt} sx={{ ml: 2, flexShrink: 0 }}>
                {improving ? "Thinking…" : "AI improve"}
              </Button>
            </Tooltip>
          </Stack>

          {loaded && (
            <MarkdownEditor ref={editorRef} initialContent={systemPrompt}
              mode={isNew ? "create" : "edit"} onChange={handleEditorChange}
              placeholder="Type the extraction rules here…" minHeight={400} />
          )}

          {aiSuggestion && (
            <Alert severity="info" sx={{ mt: 2 }} onClose={() => setAiSuggestion(null)}
              action={
                <Button size="small" onClick={() => {
                  editorRef.current?.setMarkdown(aiSuggestion);
                  setSystemPrompt(aiSuggestion);
                  setAiSuggestion(null);
                }}>Use this</Button>
              }>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.78rem" }}>
                {aiSuggestion}
              </Typography>
            </Alert>
          )}
        </Box>
      )}

      {/* ── Tab 1: Output format ────────────────────────────────────────── */}
      {tab === 1 && (
        <Box sx={{ pt: 2 }}>
          <Alert severity="info" sx={{ mb: 2.5 }} icon={<InfoOutlinedIcon />}>
            <Typography variant="body2" fontWeight={600} gutterBottom>
              This defines what the AI must output
            </Typography>
            <Typography variant="body2">
              Stored separately from the instructions and automatically appended at runtime.
              The no-code pipeline builder reads this to understand what fields flow out of this step.
              Switch to JSON view if you need to edit the raw schema.
            </Typography>
          </Alert>

          <SchemaBuilder
            value={outputSchema}
            onChange={setOutputSchema}
          />
        </Box>
      )}

      {/* ── Tab 2: Teaching examples ────────────────────────────────────── */}
      {tab === 2 && (
        <Box sx={{ pt: 2 }}>
          {/* Toolbar */}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems="center" sx={{ mb: 2 }}>
            <Stack direction="row" spacing={0.5} alignItems="center">
              <FilterListIcon sx={{ fontSize: 18, color: "text.disabled" }} />
              <Typography variant="caption" color="text.secondary">Filter:</Typography>
            </Stack>
            <FormControl size="small" sx={{ minWidth: 210 }}>
              <InputLabel>Category</InputLabel>
              <Select label="Category" value={filterCat} onChange={(e) => setFilterCat(e.target.value)}>
                {CATEGORY_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ width: "100%" }}>
                      <span>{o.label}</span>
                      {o.value && catCounts[o.value] !== undefined && (
                        <Chip size="small" label={catCounts[o.value]}
                          sx={{ height: 16, fontSize: "0.65rem", ml: 1 }} />
                      )}
                    </Stack>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 160 }}>
              <InputLabel>Provider</InputLabel>
              <Select label="Provider" value={filterScope} onChange={(e) => setFilterScope(e.target.value)}>
                <MenuItem value="">All providers</MenuItem>
                {SCOPE_OPTIONS.map((o) => (
                  <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <Box sx={{ flex: 1 }} />
            <Typography variant="caption" color="text.secondary">
              {filteredExamples.length} of {fewShotExamples.length} shown
            </Typography>
            <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={addExample}>
              Add example
            </Button>
          </Stack>

          {/* Category summary badges */}
          {fewShotExamples.length > 0 && (
            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
              {Object.entries(catCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([cat, count]) => (
                  <Chip
                    key={cat}
                    size="small"
                    label={`${categoryLabel(cat)} ${count}`}
                    color={categoryColor(cat)}
                    variant={filterCat === cat ? "filled" : "outlined"}
                    onClick={() => setFilterCat(filterCat === cat ? "" : cat)}
                    sx={{ cursor: "pointer", fontSize: "0.68rem", height: 22 }}
                  />
                ))}
            </Stack>
          )}

          <Divider sx={{ mb: 2 }} />

          {filteredExamples.length === 0 ? (
            <Box sx={{ textAlign: "center", py: 5, border: "1px dashed", borderColor: "divider", borderRadius: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                {fewShotExamples.length === 0
                  ? "No examples yet. Add one to help the AI understand what you expect."
                  : "No examples match the current filter."}
              </Typography>
              {fewShotExamples.length === 0 && (
                <Button size="small" startIcon={<AddIcon />} onClick={addExample} sx={{ mt: 1 }}>
                  Add first example
                </Button>
              )}
            </Box>
          ) : (
            filteredExamples.map((ex, idx) => (
              <ExampleCard key={ex.id} ex={ex} idx={idx}
                onChange={updateExample} onRemove={removeExample}
                startInEdit={!ex.input && !ex.output} />
            ))
          )}
        </Box>
      )}
    </Box>
  );
}
