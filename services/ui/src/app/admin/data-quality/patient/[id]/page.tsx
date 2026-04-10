'use client';

import React, { useEffect, useState } from 'react';
import { use } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  Typography,
} from '@mui/material';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import { dqApi, EpisodeSummary, EncounterSummary, PatientSummary } from '@/lib/api/dq';

// ---------------------------------------------------------------------------
// Assertion colour chip
// ---------------------------------------------------------------------------

const ASSERTION_COLORS: Record<string, 'success' | 'error' | 'warning' | 'default'> = {
  present: 'success',
  absent: 'error',
  possible: 'warning',
};

function AssertionChip({ assertion }: { assertion: string | null }) {
  if (!assertion) return null;
  const color = ASSERTION_COLORS[assertion] ?? 'default';
  return <Chip label={assertion} color={color} size="small" sx={{ ml: 0.5 }} />;
}

// ---------------------------------------------------------------------------
// Episode card
// ---------------------------------------------------------------------------

function EpisodeCard({ ep }: { ep: EpisodeSummary }) {
  const statusColor = ep.status.includes('stale') ? 'error' :
    ep.status === 'in_progress' ? 'warning' :
    ep.status === 'completed' ? 'success' : 'default';

  return (
    <Card variant="outlined" sx={{ mb: 1 }}>
      <CardContent sx={{ py: 1.5 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="subtitle2">{ep.site || 'Unknown site'}</Typography>
          <Chip label={ep.status} color={statusColor} size="small" />
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block">
          Referral: {ep.referral_date ?? 'n/a'} &nbsp;|&nbsp;
          Specialist: {ep.specialist_date ?? 'n/a'}
        </Typography>
        {ep.hitl_flag && (
          <Chip label={`HITL: ${ep.hitl_reason ?? 'flagged'}`} color="info" size="small" sx={{ mt: 0.5 }} />
        )}
        {ep.auto_closed && (
          <Chip label="Auto-closed" color="default" size="small" sx={{ mt: 0.5, ml: 0.5 }} />
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Encounter row
// ---------------------------------------------------------------------------

function EncounterRow({ enc }: { enc: EncounterSummary }) {
  return (
    <Box sx={{ mb: 2, borderLeft: '3px solid', borderColor: 'grey.300', pl: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>{enc.date}</Typography>
        {enc.classification && <Chip label={enc.classification} size="small" variant="outlined" />}
      </Stack>
      {enc.coded_concepts.length > 0 && (
        <Box mb={0.5}>
          {enc.coded_concepts.map((c, i) => (
            <Box key={i} component="span" sx={{ display: 'inline-block', mr: 1, mb: 0.5 }}>
              <Typography variant="caption">{c.name}</Typography>
              <AssertionChip assertion={c.assertion} />
            </Box>
          ))}
        </Box>
      )}
      {enc.text_preview && (
        <Typography variant="caption" color="text.secondary" fontStyle="italic">
          {enc.text_preview}
        </Typography>
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function PatientInspectorPage({ params }: PageProps) {
  const { id } = use(params);
  const [data, setData] = useState<PatientSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dqApi.getPatient(id, true)
      .then(setData)
      .catch(e => setError(String(e)));
  }, [id]);

  if (error) return <Alert severity="error" sx={{ m: 3 }}>{error}</Alert>;
  if (!data) return <Box display="flex" justifyContent="center" p={6}><CircularProgress /></Box>;

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <PersonOutlineIcon />
        <Typography variant="h5" fontWeight={700}>{id}</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={3}>
        {data.encounter_count} encounters &nbsp;|&nbsp; {data.episode_count} episodes
      </Typography>

      <Grid container spacing={3}>
        {/* Left: encounter timeline */}
        <Grid size={{ xs: 12, md: 7 }}>
          <Typography variant="h6" fontWeight={600} mb={2}>Encounter timeline</Typography>
          {data.encounters.length === 0
            ? <Typography color="text.secondary">No encounters</Typography>
            : data.encounters.map(enc => <EncounterRow key={enc.encounter_id} enc={enc} />)}
        </Grid>

        {/* Right: episodes */}
        <Grid size={{ xs: 12, md: 5 }}>
          <Typography variant="h6" fontWeight={600} mb={2}>Episodes</Typography>
          {data.episodes.length === 0
            ? <Typography color="text.secondary">No episodes</Typography>
            : data.episodes.map(ep => <EpisodeCard key={ep.episode_id} ep={ep} />)}

          <Divider sx={{ my: 3 }} />

          <Typography variant="h6" fontWeight={600} mb={2}>Coded concepts</Typography>
          {data.encounters.flatMap(enc => enc.coded_concepts).length === 0
            ? <Typography color="text.secondary">None</Typography>
            : (
              <Box>
                {data.encounters
                  .flatMap(enc => enc.coded_concepts)
                  .filter((c, i, arr) => arr.findIndex(x => x.concept_id === c.concept_id) === i)
                  .map(c => (
                    <Stack key={c.concept_id} direction="row" spacing={1} alignItems="center" mb={0.5}>
                      <Typography variant="body2">{c.name}</Typography>
                      <Typography variant="caption" color="text.secondary"><code>{c.concept_id}</code></Typography>
                      {c.semantic_tag && <Chip label={c.semantic_tag} size="small" variant="outlined" />}
                    </Stack>
                  ))}
              </Box>
            )}
        </Grid>
      </Grid>
    </Box>
  );
}
