"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import RefreshIcon from "@mui/icons-material/Refresh";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";

interface ExtractorStatus {
  backend: string;
  strict: boolean;
  model_name: string;
  model_version: string;
  model_endpoint: string;
  fallback_enabled: boolean;
}

interface ModelEntry {
  name: string;
  provider: string;
  type: "llm" | "ner" | "ml";
  status: "active" | "available" | "unavailable";
  envVar: string;
  value: string;
}

const STATIC_MODELS: Omit<ModelEntry, "status" | "value">[] = [
  { name: "Claude 3 Haiku", provider: "AWS Bedrock", type: "llm", envVar: "AWS_SMALL_MODEL" },
  { name: "Claude 3.7 Sonnet", provider: "AWS Bedrock", type: "llm", envVar: "AWS_BIG_MODEL" },
  { name: "Claude 4 Opus", provider: "AWS Bedrock", type: "llm", envVar: "AWS_MAX_MODEL" },
  { name: "GPT-5-mini", provider: "Azure OpenAI", type: "llm", envVar: "AZURE_SMALL_MODEL" },
  { name: "GPT-5", provider: "Azure OpenAI", type: "llm", envVar: "AZURE_BIG_MODEL" },
  { name: "NER Model", provider: "Custom", type: "ner", envVar: "CODING_MODEL_NAME" },
];

const TYPE_COLORS: Record<string, "primary" | "secondary" | "warning"> = {
  llm: "primary",
  ner: "secondary",
  ml: "warning",
};

export default function ModelsPage() {
  const [extractor, setExtractor] = useState<ExtractorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch("/api/pipeline/extractor-status", {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      setExtractor(await resp.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load extractor status");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const models: ModelEntry[] = STATIC_MODELS.map((m) => {
    let status: ModelEntry["status"] = "available";
    let value = "";

    if (m.type === "ner" && extractor) {
      value = extractor.model_name || "";
      status = extractor.backend === "model" || extractor.backend === "auto" ? "active" : "unavailable";
    } else if (m.type === "llm") {
      status = "active";
      value = m.envVar;
    }

    return { ...m, status, value };
  });

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.5 }}>
        <Stack direction="row" alignItems="center" spacing={1}>
          <SmartToyOutlinedIcon color="primary" />
          <Typography variant="h5" fontWeight={600}>Model Registry</Typography>
        </Stack>
        <Tooltip title="Refresh">
          <IconButton onClick={load} disabled={loading}>
            {loading ? <CircularProgress size={20} /> : <RefreshIcon />}
          </IconButton>
        </Tooltip>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        LLM, NER, and ML models available to the pipeline. LLM models are configured via
        environment variables. NER models are deployed as separate inference endpoints.
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {extractor && (
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Active Extraction Backend</Typography>
          <Stack direction="row" spacing={2} flexWrap="wrap">
            <Chip
              label={`Backend: ${extractor.backend}`}
              color={extractor.backend === "llm" ? "primary" : "secondary"}
              size="small"
            />
            <Chip
              label={extractor.strict ? "Strict mode" : "Fallback enabled"}
              color={extractor.strict ? "warning" : "success"}
              size="small"
              variant="outlined"
            />
            {extractor.model_name && (
              <Chip label={`NER: ${extractor.model_name}`} size="small" variant="outlined" />
            )}
          </Stack>
        </Paper>
      )}

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Model</TableCell>
              <TableCell>Provider</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Config</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {models.map((m) => (
              <TableRow key={m.envVar}>
                <TableCell>
                  <Typography variant="body2" fontWeight={500}>{m.name}</Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="caption" color="text.secondary">{m.provider}</Typography>
                </TableCell>
                <TableCell>
                  <Chip label={m.type.toUpperCase()} size="small" color={TYPE_COLORS[m.type] || "default"} variant="outlined" />
                </TableCell>
                <TableCell>
                  {m.status === "active" ? (
                    <Chip icon={<CheckCircleOutlineIcon />} label="Active" size="small" color="success" variant="outlined" />
                  ) : m.status === "unavailable" ? (
                    <Chip icon={<ErrorOutlineIcon />} label="Unavailable" size="small" color="default" variant="outlined" />
                  ) : (
                    <Chip label="Available" size="small" variant="outlined" />
                  )}
                </TableCell>
                <TableCell>
                  <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                    {m.envVar}
                  </Typography>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 2 }}>
        LLM model selections are configured via environment variables on the pipeline worker.
        Custom ML models (length of stay, risk prediction) will appear here once deployed.
      </Typography>
    </Box>
  );
}
