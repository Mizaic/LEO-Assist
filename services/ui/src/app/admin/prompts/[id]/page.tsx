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
import Collapse from "@mui/material/Collapse";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SaveIcon from "@mui/icons-material/Save";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import MarkdownEditor from "@/components/markdown-editor";
import type { MarkdownEditorHandle } from "@/components/markdown-editor";
import { api } from "@/lib/api";

interface FewShotExample {
  id: string;
  input: string;
  output: string;
  deidentified: boolean;
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

export default function PromptTunerPage() {
  const params   = useParams();
  const router   = useRouter();
  const promptId = params.id as string;
  const isNew    = promptId === "new";

  const editorRef = useRef<MarkdownEditorHandle>(null);

  const [name,            setName]            = useState("");
  const [description,     setDescription]     = useState("");
  const [systemPrompt,    setSystemPrompt]    = useState("");   // kept in sync with editor
  const [outputSchema,    setOutputSchema]    = useState("{}");
  const [showAdvanced,    setShowAdvanced]    = useState(false);
  const [verification,    setVerification]    = useState(false);
  const [fewShotExamples, setFewShotExamples] = useState<FewShotExample[]>([]);
  const [aiSuggestion,    setAiSuggestion]    = useState<string | null>(null);
  const [improving,       setImproving]       = useState(false);
  const [saving,          setSaving]          = useState(false);
  const [version,         setVersion]         = useState<number | null>(null);
  const [loaded,          setLoaded]          = useState(false);

  useEffect(() => {
    if (!isNew) {
      api.get<PromptConfigData>(`/api/prompts/${promptId}`)
        .then((data) => {
          setName(data.name);
          setDescription(data.description || "");
          setSystemPrompt(data.systemPrompt);
          setOutputSchema(data.outputSchema || "{}");
          setVerification(data.verification);
          setFewShotExamples(data.fewShotExamples || []);
          setVersion(data.version);
          setLoaded(true);
        })
        .catch(() => setLoaded(true));
    } else {
      setLoaded(true);
    }
  }, [promptId, isNew]);

  // Once the editor mounts and data is loaded, push the initial content in
  useEffect(() => {
    if (loaded && systemPrompt) {
      editorRef.current?.setMarkdown(systemPrompt);
    }
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
  }, [name, systemPrompt, outputSchema, verification, fewShotExamples, isNew, promptId, router]);

  const addExample = useCallback(() => {
    setFewShotExamples((prev) => [
      ...prev,
      { id: `ex_${Date.now()}`, input: "", output: "", deidentified: false },
    ]);
  }, []);

  const removeExample = useCallback((id: string) => {
    setFewShotExamples((prev) => prev.filter((e) => e.id !== id));
  }, []);

  const updateExample = useCallback(
    (id: string, field: keyof FewShotExample, value: string | boolean) => {
      setFewShotExamples((prev) =>
        prev.map((e) => (e.id === id ? { ...e, [field]: value } : e)),
      );
    },
    [],
  );

  return (
    <Box sx={{ p: 3, maxWidth: 860, mx: "auto" }}>
      {/* Page header */}
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 3 }}>
        <IconButton onClick={() => router.push("/admin/prompts")} aria-label="Back to instructions">
          <ArrowBackIcon />
        </IconButton>
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" fontWeight={700}>
            {isNew ? "New AI instructions" : "Edit AI instructions"}
          </Typography>
          {!isNew && version !== null && (
            <Typography variant="caption" color="text.secondary">
              Current version: v{version}
            </Typography>
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

      {/* Name */}
      <Paper variant="outlined" sx={{ p: 2.5, mb: 2.5, borderRadius: 2 }}>
        <Typography variant="subtitle2" fontWeight={600} gutterBottom>
          Instructions name
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          Give these instructions a short, clear name so you can find them later.
        </Typography>
        <TextField
          fullWidth size="small"
          placeholder="e.g. Standard clinical coder, Referral letter extractor"
          value={name}
          onChange={(e) => setName(e.target.value)}
          sx={{ mb: 2 }}
        />
        <Typography variant="subtitle2" fontWeight={600} gutterBottom>
          What is this for?
        </Typography>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          A plain English summary of what these instructions do — shown on the cards page so your team knows which one to use.
        </Typography>
        <TextField
          fullWidth size="small" multiline rows={2}
          placeholder="e.g. Extracts clinical entities and SNOMED codes from referral letters. Used as the main extraction step in the clinical coding pipeline."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Paper>

      {/* System prompt — WYSIWYG */}
      <Paper variant="outlined" sx={{ p: 2.5, mb: 2.5, borderRadius: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
          <Typography variant="subtitle2" fontWeight={600}>
            What should the AI do?
          </Typography>
          <Tooltip title="Use the AI assistant to review and improve these instructions based on past results.">
            <Button
              size="small"
              variant="outlined"
              startIcon={improving ? <CircularProgress size={14} /> : <AutoFixHighIcon />}
              onClick={handleAiImprove}
              disabled={improving || !systemPrompt}
              sx={{ flexShrink: 0 }}
            >
              {improving ? "Thinking…" : "AI improve"}
            </Button>
          </Tooltip>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
          Write the instructions the AI follows when it reads clinical text. You can use bullet points,
          headings, and bold text to organise your instructions clearly.
        </Typography>

        {loaded && (
          <MarkdownEditor
            ref={editorRef}
            initialContent={systemPrompt}
            mode={isNew ? "create" : "edit"}
            onChange={handleEditorChange}
            placeholder="Type your instructions here…"
            minHeight={280}
          />
        )}

        {/* AI suggestion */}
        {aiSuggestion && (
          <Alert
            severity="info"
            sx={{ mt: 2 }}
            onClose={() => setAiSuggestion(null)}
            action={
              <Button
                size="small"
                onClick={() => {
                  editorRef.current?.setMarkdown(aiSuggestion);
                  setSystemPrompt(aiSuggestion);
                  setAiSuggestion(null);
                }}
              >
                Use this
              </Button>
            }
          >
            <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.8rem" }}>
              {aiSuggestion}
            </Typography>
          </Alert>
        )}
      </Paper>

      {/* Double-check toggle */}
      <Paper variant="outlined" sx={{ p: 2.5, mb: 2.5, borderRadius: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="subtitle2" fontWeight={600} gutterBottom>
              Double-check results
            </Typography>
            <Typography variant="caption" color="text.secondary">
              When turned on, a second AI check runs after the first to confirm the answer is correct
              before saving.
            </Typography>
          </Box>
          <FormControlLabel
            control={
              <Switch
                checked={verification}
                onChange={(e) => setVerification(e.target.checked)}
                color="success"
              />
            }
            label={
              verification
                ? <Chip size="small" label="On" color="success" icon={<CheckCircleOutlineIcon />} />
                : <Typography variant="caption" color="text.secondary">Off</Typography>
            }
            labelPlacement="start"
            sx={{ m: 0 }}
          />
        </Stack>
      </Paper>

      {/* Advanced — collapsed by default */}
      <Box sx={{ mb: 2.5 }}>
        <Button
          size="small"
          variant="text"
          color="inherit"
          onClick={() => setShowAdvanced((v) => !v)}
          endIcon={
            <ExpandMoreIcon
              sx={{ transition: "transform 0.2s", transform: showAdvanced ? "rotate(180deg)" : "rotate(0deg)" }}
            />
          }
          sx={{ color: "text.disabled", fontSize: "0.78rem" }}
          startIcon={<InfoOutlinedIcon sx={{ fontSize: 15 }} />}
        >
          Advanced settings
        </Button>
        <Collapse in={showAdvanced}>
          <Paper variant="outlined" sx={{ p: 2.5, mt: 1, borderRadius: 2, borderStyle: "dashed" }}>
            <Typography variant="subtitle2" fontWeight={600} gutterBottom>
              Output schema (advanced)
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
              Optional. Most prompts define their output format inside the instructions above —
              you usually don&apos;t need to change this. Only edit if you know what you are doing.
            </Typography>
            <TextField
              fullWidth multiline minRows={3} maxRows={10} size="small"
              value={outputSchema}
              onChange={(e) => setOutputSchema(e.target.value)}
              inputProps={{ style: { fontFamily: "monospace", fontSize: "0.82rem" } }}
            />
          </Paper>
        </Collapse>
      </Box>

      <Divider sx={{ mb: 2.5 }} />

      {/* Few-shot examples */}
      <Box>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
          <Box>
            <Typography variant="subtitle2" fontWeight={600}>Teaching examples</Typography>
            <Typography variant="caption" color="text.secondary">
              Show the AI a real piece of text and the correct answer. This helps it learn what good looks like.
            </Typography>
          </Box>
          <Button size="small" startIcon={<AddIcon />} onClick={addExample}>Add example</Button>
        </Stack>

        {fewShotExamples.length === 0 && (
          <Box
            sx={{
              textAlign: "center", py: 4, px: 3,
              border: "1px dashed", borderColor: "divider", borderRadius: 2,
            }}
          >
            <Typography variant="body2" color="text.secondary">
              No teaching examples yet. Add one to help the AI understand what you expect.
            </Typography>
          </Box>
        )}

        {fewShotExamples.map((ex, idx) => (
          <Card key={ex.id} variant="outlined" sx={{ mb: 2, borderRadius: 2 }}>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
                <Typography variant="caption" fontWeight={600} color="text.secondary">
                  Example {idx + 1}
                </Typography>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={ex.deidentified}
                        onChange={(e) => updateExample(ex.id, "deidentified", e.target.checked)}
                        color="success"
                      />
                    }
                    label={
                      <Typography variant="caption" color={ex.deidentified ? "success.main" : "text.secondary"}>
                        {ex.deidentified ? "Names removed ✓" : "Remove names?"}
                      </Typography>
                    }
                    sx={{ m: 0 }}
                  />
                  <IconButton size="small" onClick={() => removeExample(ex.id)} aria-label="Remove example">
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Stack>
              </Stack>

              <TextField
                fullWidth size="small"
                label="Clinical text (what the AI sees)"
                multiline minRows={2}
                value={ex.input}
                onChange={(e) => updateExample(ex.id, "input", e.target.value)}
                sx={{ mb: 1.5 }}
                helperText={!ex.deidentified && ex.input ? "⚠ Make sure no patient names or NHS numbers are in here." : undefined}
                FormHelperTextProps={{ sx: { color: "warning.main" } }}
              />
              <TextField
                fullWidth size="small"
                label="Correct answer (what the AI should say)"
                multiline minRows={2}
                value={ex.output}
                onChange={(e) => updateExample(ex.id, "output", e.target.value)}
                inputProps={{ style: { fontFamily: "monospace", fontSize: "0.82rem" } }}
              />
            </CardContent>
          </Card>
        ))}
      </Box>
    </Box>
  );
}
