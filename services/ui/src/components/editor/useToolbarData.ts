'use client';

import { useEffect, useMemo, useState } from 'react';
import { getOrganizations, getPatients } from '@/lib/api';
import type { Organization, Patient } from '@/lib/types/fhir';
import type { CohortFilters } from '@/lib/types/layout';

// ── Option label type ────────────────────────────────────────────────────────

export interface OptionLabel {
  id: string;
  label: string;
}

// ── Organization options hook ────────────────────────────────────────────────

interface UseOrgOptionsResult {
  orgQuery: string;
  setOrgQuery: (query: string) => void;
  orgOptionLabels: OptionLabel[];
  orgLoading: boolean;
}

export function useOrganizationOptions(
  isDev: boolean,
  reportScope: 'patient' | 'organization'
): UseOrgOptionsResult {
  const [orgQuery, setOrgQuery] = useState('');
  const [orgOptions, setOrgOptions] = useState<Organization[]>([]);
  const [orgLoading, setOrgLoading] = useState(false);

  useEffect(() => {
    if (!isDev || reportScope !== 'organization') return;
    const handle = window.setTimeout(async () => {
      try {
        setOrgLoading(true);
        const bundle = await getOrganizations({ name: orgQuery, _count: 200 });
        const resources =
          (bundle.entry?.map((entry) => entry.resource).filter(Boolean) as Organization[]) || [];
        setOrgOptions(resources);
      } catch (error) {
        console.error('Failed to load organizations:', error);
        setOrgOptions([]);
      } finally {
        setOrgLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [isDev, orgQuery, reportScope]);

  const sortedOrgOptions = useMemo(() => {
    return [...orgOptions].sort((a, b) => {
      const aLabel = (a.name || a.id || '').toLowerCase();
      const bLabel = (b.name || b.id || '').toLowerCase();
      if (aLabel < bLabel) return -1;
      if (aLabel > bLabel) return 1;
      return 0;
    });
  }, [orgOptions]);

  const orgOptionLabels = useMemo<OptionLabel[]>(() => {
    return sortedOrgOptions.map((org) => {
      const id = org.id || '';
      const name = org.name || id;
      return { id, label: name && id && name !== id ? `${name} (${id})` : name };
    });
  }, [sortedOrgOptions]);

  return { orgQuery, setOrgQuery, orgOptionLabels, orgLoading };
}

// ── Patient options hook ─────────────────────────────────────────────────────

interface UsePatientOptionsResult {
  patientQuery: string;
  setPatientQuery: (query: string) => void;
  patientOptionLabels: OptionLabel[];
  patientLoading: boolean;
}

export function usePatientOptions(
  isDev: boolean,
  reportScope: 'patient' | 'organization'
): UsePatientOptionsResult {
  const [patientQuery, setPatientQuery] = useState('');
  const [patientOptions, setPatientOptions] = useState<Patient[]>([]);
  const [patientLoading, setPatientLoading] = useState(false);

  useEffect(() => {
    if (!isDev || reportScope !== 'patient') return;
    const handle = window.setTimeout(async () => {
      try {
        setPatientLoading(true);
        const bundle = await getPatients({ name: patientQuery, _count: 200 });
        const resources =
          (bundle.entry?.map((entry) => entry.resource).filter(Boolean) as Patient[]) || [];
        setPatientOptions(resources);
      } catch (error) {
        console.error('Failed to load patients:', error);
        setPatientOptions([]);
      } finally {
        setPatientLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [isDev, patientQuery, reportScope]);

  const patientOptionLabels = useMemo<OptionLabel[]>(() => {
    return patientOptions.map((patient) => {
      const id = patient.id || '';
      const name =
        patient.name?.[0]?.text ||
        [patient.name?.[0]?.given?.join(' '), patient.name?.[0]?.family]
          .filter(Boolean)
          .join(' ')
          .trim() ||
        id;
      return { id, label: name && id && name !== id ? `${name} (${id})` : name };
    });
  }, [patientOptions]);

  return { patientQuery, setPatientQuery, patientOptionLabels, patientLoading };
}

// ── Cohort filter derived values ─────────────────────────────────────────────

interface CohortFilterValues {
  cohortStatusValue: string;
  excludedStatusValue: string;
  cancerTypeValue: string;
}

export function useCohortFilterValues(cohortFilters: CohortFilters): CohortFilterValues {
  const cohortStatusValue = useMemo(() => {
    const status = cohortFilters.ce_status || [];
    if (status.length === 0) return 'all';
    if (status.length === 1) return status[0];
    return 'custom';
  }, [cohortFilters.ce_status]);

  const excludedStatusValue = useMemo(
    () => (cohortFilters.ce_status_exclude || []).join(', '),
    [cohortFilters.ce_status_exclude]
  );

  const cancerTypeValue = useMemo(
    () => (cohortFilters.ce_condition_type || []).join(', '),
    [cohortFilters.ce_condition_type]
  );

  return { cohortStatusValue, excludedStatusValue, cancerTypeValue };
}
