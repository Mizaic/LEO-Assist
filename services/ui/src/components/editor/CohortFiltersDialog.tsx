'use client';

import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import type { CohortFilters } from '@/lib/types/layout';

// ── Types ────────────────────────────────────────────────────────────────────

export interface CohortFiltersDialogProps {
  open: boolean;
  onClose: () => void;
  cohortFilters: CohortFilters;
  cohortStatusValue: string;
  excludedStatusValue: string;
  cancerTypeValue: string;
  onUpdateCohortFilters: (updates: Partial<CohortFilters>) => void;
  onClearCohortFilters: () => void;
}

// ── Shared field-column style ────────────────────────────────────────────────

const fieldColumnSx = {
  display: 'flex',
  flexDirection: 'column' as const,
  gap: 0.5,
  minWidth: '140px',
};

const labelSx = { fontSize: '0.625rem', color: 'text.secondary' };

const dateGridSx = { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1 };

// ── Outcome filter row ───────────────────────────────────────────────────────

function OutcomeFilter({
  value,
  onChange,
}: {
  value: string;
  onChange: (updates: Partial<CohortFilters>) => void;
}) {
  const handleChange = (selected: string) => {
    if (selected === 'all') return onChange({ ce_status: undefined });
    if (selected === 'custom') return onChange({ ce_status: [] });
    return onChange({ ce_status: [selected] });
  };

  return (
    <Box sx={fieldColumnSx}>
      <Typography sx={labelSx}>Outcome</Typography>
      <TextField
        select
        size="small"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
        aria-label="Outcome filter"
      >
        <MenuItem value="all">Entire cohort</MenuItem>
        <MenuItem value="confirmed">Diagnosed</MenuItem>
        <MenuItem value="excluded">Cancer excluded</MenuItem>
        <MenuItem value="inconclusive">Inconclusive</MenuItem>
        <MenuItem value="pending">Pending/unknown</MenuItem>
      </TextField>
    </Box>
  );
}

// ── Comma-separated text filter row ──────────────────────────────────────────

function CommaSeparatedFilter({
  label,
  placeholder,
  value,
  filterKey,
  onChange,
}: {
  label: string;
  placeholder: string;
  value: string;
  filterKey: keyof CohortFilters;
  onChange: (updates: Partial<CohortFilters>) => void;
}) {
  return (
    <Box sx={fieldColumnSx}>
      <Typography sx={labelSx}>{label}</Typography>
      <TextField
        size="small"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          const parsed = (e.target.value || '')
            .split(',')
            .map((entry) => entry.trim())
            .filter(Boolean);
          onChange({ [filterKey]: parsed.length ? parsed : undefined });
        }}
      />
    </Box>
  );
}

// ── Date range filter row ────────────────────────────────────────────────────

function DateRangeFilter({
  label,
  startKey,
  endKey,
  startValue,
  endValue,
  onChange,
}: {
  label: string;
  startKey: keyof CohortFilters;
  endKey: keyof CohortFilters;
  startValue: string;
  endValue: string;
  onChange: (updates: Partial<CohortFilters>) => void;
}) {
  return (
    <Box sx={fieldColumnSx}>
      <Typography sx={labelSx}>{label}</Typography>
      <Box sx={dateGridSx}>
        <TextField
          size="small"
          type="date"
          value={startValue}
          onChange={(e) => onChange({ [startKey]: e.target.value || undefined })}
        />
        <TextField
          size="small"
          type="date"
          value={endValue}
          onChange={(e) => onChange({ [endKey]: e.target.value || undefined })}
        />
      </Box>
    </Box>
  );
}

// ── Main dialog ──────────────────────────────────────────────────────────────

export function CohortFiltersDialog({
  open,
  onClose,
  cohortFilters,
  cohortStatusValue,
  excludedStatusValue,
  cancerTypeValue,
  onUpdateCohortFilters,
  onClearCohortFilters,
}: CohortFiltersDialogProps) {
  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>Cohort filters</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, pt: 1 }}>
          <OutcomeFilter value={cohortStatusValue} onChange={onUpdateCohortFilters} />

          <CommaSeparatedFilter
            label="Exclude outcomes"
            placeholder="e.g. pending, inconclusive"
            value={excludedStatusValue}
            filterKey="ce_status_exclude"
            onChange={onUpdateCohortFilters}
          />

          <CommaSeparatedFilter
            label="Cancer type"
            placeholder="e.g. Breast, Lung"
            value={cancerTypeValue}
            filterKey="ce_condition_type"
            onChange={onUpdateCohortFilters}
          />

          <Box sx={fieldColumnSx}>
            <Typography sx={labelSx}>Agent confidence</Typography>
            <TextField
              size="small"
              type="number"
              inputProps={{ step: '0.01', min: '0', max: '1' }}
              value={
                cohortFilters.ce_agent_confidence != null
                  ? String(cohortFilters.ce_agent_confidence)
                  : ''
              }
              onChange={(e) => {
                const raw = e.target.value;
                onUpdateCohortFilters({ ce_agent_confidence: raw ? Number(raw) : undefined });
              }}
            />
          </Box>

          <DateRangeFilter
            label="Created at"
            startKey="ce_created_at_start"
            endKey="ce_created_at_end"
            startValue={cohortFilters.ce_created_at_start || ''}
            endValue={cohortFilters.ce_created_at_end || ''}
            onChange={onUpdateCohortFilters}
          />
          <DateRangeFilter
            label="First encounter"
            startKey="ce_first_encounter_date_start"
            endKey="ce_first_encounter_date_end"
            startValue={cohortFilters.ce_first_encounter_date_start || ''}
            endValue={cohortFilters.ce_first_encounter_date_end || ''}
            onChange={onUpdateCohortFilters}
          />
          <DateRangeFilter
            label="Last encounter"
            startKey="ce_last_encounter_date_start"
            endKey="ce_last_encounter_date_end"
            startValue={cohortFilters.ce_last_encounter_date_start || ''}
            endValue={cohortFilters.ce_last_encounter_date_end || ''}
            onChange={onUpdateCohortFilters}
          />
          <DateRangeFilter
            label="Referral date"
            startKey="ce_referral_date_start"
            endKey="ce_referral_date_end"
            startValue={cohortFilters.ce_referral_date_start || ''}
            endValue={cohortFilters.ce_referral_date_end || ''}
            onChange={onUpdateCohortFilters}
          />
          <DateRangeFilter
            label="Diagnosis date"
            startKey="ce_diagnosis_date_start"
            endKey="ce_diagnosis_date_end"
            startValue={cohortFilters.ce_diagnosis_date_start || ''}
            endValue={cohortFilters.ce_diagnosis_date_end || ''}
            onChange={onUpdateCohortFilters}
          />
          <DateRangeFilter
            label="Treatment start"
            startKey="ce_treatment_start_date_start"
            endKey="ce_treatment_start_date_end"
            startValue={cohortFilters.ce_treatment_start_date_start || ''}
            endValue={cohortFilters.ce_treatment_start_date_end || ''}
            onChange={onUpdateCohortFilters}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button variant="outlined" onClick={onClearCohortFilters}>
          Clear filters
        </Button>
        <Button variant="contained" onClick={onClose}>
          Done
        </Button>
      </DialogActions>
    </Dialog>
  );
}
