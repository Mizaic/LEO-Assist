/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import FormControl from '@mui/material/FormControl';
import FormLabel from '@mui/material/FormLabel';
import MenuItem from '@mui/material/MenuItem';
import Select from '@mui/material/Select';
import Step from '@mui/material/Step';
import StepLabel from '@mui/material/StepLabel';
import Stepper from '@mui/material/Stepper';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import ArrowBackOutlined from '@mui/icons-material/ArrowBackOutlined';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import OpenInNewOutlined from '@mui/icons-material/OpenInNewOutlined';
import { uploadBenchmarks, inferBenchmarkStructure } from '@/lib/api';

const STEPS = ['Upload', 'Inspect', 'Map', 'Preview & Save'];
const TEMPLATES = [
  { id: 'ncda', label: 'NCDA (National Cancer Diagnosis Audit)' },
];

export function BenchmarkUploadWizard() {
  const router = useRouter();
  const [activeStep, setActiveStep] = useState(0);
  const [rawJson, setRawJson] = useState<Record<string, unknown> | null>(null);
  const [structure, setStructure] = useState<{ keys: string[]; sample: Record<string, unknown>; depth: number } | null>(null);
  const [templateId, setTemplateId] = useState('ncda');
  const [name, setName] = useState('');
  const [auditId, setAuditId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ audit_id: string; count: number } | null>(null);

  const handleJsonInput = (text: string) => {
    setError(null);
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      setRawJson(parsed);
    } catch {
      setError('Invalid JSON – please check the pasted content.');
      setRawJson(null);
    }
  };

  const handleInspect = async () => {
    if (!rawJson) return;
    setError(null);
    try {
      const result = await inferBenchmarkStructure(rawJson);
      setStructure(result);
      setActiveStep(1);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to infer structure');
    }
  };

  const handleInspectToMap = () => {
    // Pre-fill from JSON metadata before showing Map step
    if (rawJson) {
      const audit = rawJson.audit as Record<string, unknown> | undefined;
      const year = audit?.year as number | undefined;
      const suggestedId = year ? `ncda-${year}` : 'uploaded';
      setAuditId((prev) => prev || suggestedId);
      setName((prev) => prev || (audit?.name as string) || suggestedId);
    }
    setActiveStep(2);
  };

  const handleSave = async () => {
    if (!rawJson) return;
    setError(null);
    setSaving(true);
    try {
      const result = await uploadBenchmarks({
        rawJson,
        templateId,
        auditId: auditId || undefined,
        name: name || undefined,
      });
      setUploadResult({ audit_id: result.audit_id, count: result.count });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save benchmarks. Check the JSON format and try again.');
    } finally {
      setSaving(false);
    }
  };

  // Success screen shown after upload
  if (uploadResult) {
    return (
      <Box sx={{ p: 3, maxWidth: 600 }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, py: 4 }}>
          <CheckCircleOutlined sx={{ fontSize: 64, color: 'success.main' }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Upload successful</Typography>
          <Typography variant="body2" color="text.secondary" align="center">
            Benchmark set <strong>{uploadResult.audit_id}</strong> was created with{' '}
            <strong>{uploadResult.count}</strong> values.
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
            <Button
              variant="contained"
              startIcon={<OpenInNewOutlined />}
              onClick={() => router.push(`/benchmarks/sets/${uploadResult.audit_id}`)}
            >
              View set
            </Button>
            <Button variant="outlined" onClick={() => router.push('/benchmarks')}>
              Back to Benchmarks
            </Button>
          </Box>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 800 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Button variant="text" startIcon={<ArrowBackOutlined />} onClick={() => router.push('/benchmarks')}>
          Back
        </Button>
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          Upload Benchmarks
        </Typography>
      </Box>

      <Stepper activeStep={activeStep} sx={{ mb: 3 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}

      {/* Step 0: Paste / upload JSON */}
      {activeStep === 0 && (
        <Card>
          <CardContent>
            <Typography sx={{ fontWeight: 600, mb: 2 }}>Upload JSON</Typography>
            <TextField
              fullWidth
              multiline
              rows={12}
              placeholder='Paste benchmark JSON (e.g. NCDA format)...'
              onChange={(e) => handleJsonInput(e.target.value)}
              error={!!error}
              helperText="Paste the full JSON content from your benchmark file."
            />
            <Button variant="contained" sx={{ mt: 2 }} onClick={handleInspect} disabled={!rawJson}>
              Next: Inspect
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 1: Inspect structure */}
      {activeStep === 1 && structure && (
        <Card>
          <CardContent>
            <Typography sx={{ fontWeight: 600, mb: 2 }}>Inspect Structure</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Detected {structure.keys.length} keys, max depth {structure.depth}.
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="text.secondary">Sample keys:</Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                {structure.keys.slice(0, 20).map((k) => (
                  <Typography key={k} component="span" variant="caption" sx={{ bgcolor: 'action.hover', px: 0.5, borderRadius: 0.5 }}>
                    {k}
                  </Typography>
                ))}
                {structure.keys.length > 20 && <Typography variant="caption">+{structure.keys.length - 20} more</Typography>}
              </Box>
            </Box>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="outlined" onClick={() => setActiveStep(0)}>Back</Button>
              <Button variant="contained" onClick={handleInspectToMap}>Next: Map</Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Map template + IDs */}
      {activeStep === 2 && (
        <Card>
          <CardContent>
            <Typography sx={{ fontWeight: 600, mb: 2 }}>Map to Schema</Typography>
            <FormControl size="small" fullWidth sx={{ mb: 2 }}>
              <FormLabel>Template</FormLabel>
              <Select value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
                {TEMPLATES.map((t) => (
                  <MenuItem key={t.id} value={t.id}>{t.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              fullWidth
              size="small"
              label="Set ID (audit_id)"
              value={auditId}
              onChange={(e) => setAuditId(e.target.value)}
              placeholder="e.g. ncda-2018"
              helperText="Unique identifier for this benchmark set. Auto-generated from the JSON if left blank."
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth
              size="small"
              label="Display Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. NCDA 2018/19"
            />
            <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
              <Button variant="outlined" onClick={() => setActiveStep(1)}>Back</Button>
              <Button variant="contained" onClick={() => setActiveStep(3)}>Next: Preview</Button>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Preview & Save */}
      {activeStep === 3 && (
        <Card>
          <CardContent>
            <Typography sx={{ fontWeight: 600, mb: 2 }}>Preview & Save</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Review the settings below before saving.
            </Typography>
            <Box sx={{ bgcolor: 'action.hover', borderRadius: 1, p: 2, mb: 2 }}>
              <Typography variant="body2"><strong>Set ID:</strong> {auditId || '(auto from JSON)'}</Typography>
              <Typography variant="body2"><strong>Display Name:</strong> {name || '(auto from JSON)'}</Typography>
              <Typography variant="body2"><strong>Template:</strong> {templateId}</Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="outlined" onClick={() => setActiveStep(2)}>Back</Button>
              <Button variant="contained" onClick={handleSave} disabled={saving}>
                {saving ? 'Uploading…' : 'Save'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
