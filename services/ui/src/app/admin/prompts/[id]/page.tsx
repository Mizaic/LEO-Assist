"use client";

import { useCallback, useEffect, useState } from "react";
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
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SaveIcon from "@mui/icons-material/Save";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
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
  version: number;
  systemPrompt: string;
  outputSchema: string;
  verification: boolean;
  fewShotExamples: FewShotExample[];
}

export default function PromptTunerPage() {
  const params = useParams();
  const router = useRouter();
  const promptId = params.id as string;
  const isNew = promptId === "new";

  const [name, setName] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [outputSchema, setOutputSchema] = useState("{}");
  const [verification, setVerification] = useState(false);
  const [fewShotExamples, setFewShotExamples] = useState<FewShotExample[]>([]);
  const [aiSuggestion, setAiSuggestion] = useState<string | null>(null);
  const [improving, setImproving] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isNew) {
      api.get<PromptConfigData>(`/api/prompts/${promptId}`)
        .then((data) => {
          setName(data.name);
          setSystemPrompt(data.systemPrompt);
          setOutputSchema(data.outputSchema || "{}");
          setVerification(data.verification);
          setFewShotExamples(data.fewShotExamples || []);
        })
        .catch(() => {});
    }
  }, [promptId, isNew]);

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
    const payload = { name, systemPrompt, outputSchema, verification, fewShotExamples };
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

  const updateExample = useCallback((id: string, field: keyof FewShotExample, value: string | boolean) => {
    setFewShotExamples((prev) => prev.map((e) => e.id === id ? { ...e, [field]: value } : e));
  }, []);

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: "auto" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 3 }}>
        <IconButton onClick={() => router.push("/admin/prompts")}><ArrowBackIcon /></IconButton>
        <Typography variant="h5" fontWeight={600}>{isNew ? "New Prompt" : "Edit Prompt"}</Typography>
        <Box sx={{ flex: 1 }} />
        <Button variant="contained" startIcon={<SaveIcon />} onClick={handleSave} disabled={saving}>
          {saving ? "Saving..." : "Save"}
        </Button>
      </Box>

      <TextField fullWidth label="Prompt Name" value={name} onChange={(e) => setName(e.target.value)} sx={{ mb: 3 }} />

      <Typography variant="subtitle1" fontWeight={600} gutterBottom>System Prompt</Typography>
      <TextField
        fullWidth multiline minRows={8} maxRows={20}
        value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)}
        sx={{ mb: 2, fontFamily: "monospace" }}
      />
      <Box sx={{ display: "flex", gap: 1, mb: 3 }}>
        <Button
          variant="outlined" startIcon={improving ? <CircularProgress size={16} /> : <AutoFixHighIcon />}
          onClick={handleAiImprove} disabled={improving || !systemPrompt}
        >
          {improving ? "Improving..." : "AI Improve"}
        </Button>
      </Box>
      {aiSuggestion && (
        <Alert severity="info" sx={{ mb: 3 }} onClose={() => setAiSuggestion(null)}
          action={<Button size="small" onClick={() => { setSystemPrompt(aiSuggestion); setAiSuggestion(null); }}>Apply</Button>}
        >
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace", fontSize: "0.8rem" }}>
            {aiSuggestion}
          </Typography>
        </Alert>
      )}

      <Typography variant="subtitle1" fontWeight={600} gutterBottom>Output Schema (JSON)</Typography>
      <TextField
        fullWidth multiline minRows={4} maxRows={10}
        value={outputSchema} onChange={(e) => setOutputSchema(e.target.value)}
        sx={{ mb: 3, fontFamily: "monospace" }}
      />

      <FormControlLabel
        control={<Switch checked={verification} onChange={(e) => setVerification(e.target.checked)} />}
        label="Enable verification step"
        sx={{ mb: 3 }}
      />

      <Divider sx={{ mb: 3 }} />

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Typography variant="subtitle1" fontWeight={600}>Few-shot Examples</Typography>
        <Button size="small" startIcon={<AddIcon />} onClick={addExample}>Add Example</Button>
      </Box>

      {fewShotExamples.map((ex) => (
        <Card key={ex.id} variant="outlined" sx={{ mb: 2 }}>
          <CardContent>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
              <Typography variant="caption" color="text.secondary">Example</Typography>
              <IconButton size="small" onClick={() => removeExample(ex.id)}><DeleteIcon fontSize="small" /></IconButton>
            </Box>
            <TextField
              fullWidth label="Input (encounter text)" multiline minRows={2}
              value={ex.input} onChange={(e) => updateExample(ex.id, "input", e.target.value)} sx={{ mb: 1 }}
            />
            <TextField
              fullWidth label="Expected Output (JSON)" multiline minRows={2}
              value={ex.output} onChange={(e) => updateExample(ex.id, "output", e.target.value)}
              sx={{ fontFamily: "monospace" }}
            />
            <FormControlLabel
              control={<Switch checked={ex.deidentified} onChange={(e) => updateExample(ex.id, "deidentified", e.target.checked)} />}
              label="De-identified" sx={{ mt: 1 }}
            />
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
