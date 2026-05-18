/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
import React from 'react';
import BarChartOutlined from '@mui/icons-material/BarChartOutlined';
import PeopleOutlined from '@mui/icons-material/PeopleOutlined';
import AltRouteOutlined from '@mui/icons-material/AltRouteOutlined';
import MedicalServicesOutlined from '@mui/icons-material/MedicalServicesOutlined';
import ScienceOutlined from '@mui/icons-material/ScienceOutlined';
import PsychologyOutlined from '@mui/icons-material/PsychologyOutlined';
import TimerOutlined from '@mui/icons-material/TimerOutlined';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import type { Measure } from '@/lib/types/fhir';

export interface MeasureCategory {
  key: string;
  label: string;
  icon: React.ReactElement;
  color: string;
}

export const CATEGORIES: MeasureCategory[] = [
  { key: 'demographics', label: 'Demographics', icon: React.createElement(PeopleOutlined), color: '#0078D4' },
  { key: 'pathways', label: 'Pathways & Intervals', icon: React.createElement(AltRouteOutlined), color: '#C239B3' },
  { key: 'clinical', label: 'Clinical', icon: React.createElement(MedicalServicesOutlined), color: '#E3008C' },
  { key: 'referrals', label: 'Referrals & Investigations', icon: React.createElement(ScienceOutlined), color: '#D83B01' },
  { key: 'symptoms', label: 'Symptom Analysis', icon: React.createElement(PsychologyOutlined), color: '#8764B8' },
  { key: 'consultations', label: 'Consultations', icon: React.createElement(TimerOutlined), color: '#00B7C3' },
  { key: 'outcomes', label: 'Outcomes', icon: React.createElement(CheckCircleOutlined), color: '#107C10' },
  { key: 'other', label: 'Other', icon: React.createElement(BarChartOutlined), color: '#69797E' },
];

const CATEGORY_MAP: Record<string, string> = {
  'age-distribution': 'demographics',
  'gender-distribution': 'demographics',
  'ethnicity-distribution': 'demographics',
  'imd-distribution': 'demographics',
  'population-pyramid': 'demographics',
  'unique-patient-count': 'demographics',
  'pathway-funnel': 'pathways',
  'pathway-milestone-transitions': 'pathways',
  'primary-care-interval': 'pathways',
  'primary-care-interval-scatter': 'pathways',
  'diagnostic-interval': 'pathways',
  'diagnostic-interval-scatter': 'pathways',
  'referral-to-diagnosis-interval': 'pathways',
  'referral-to-diagnosis-interval-scatter': 'pathways',
  'comorbidities-summary': 'clinical',
  'comorbidities-detail': 'clinical',
  'charlson-comorbidity-index': 'clinical',
  'cancer-stage-distribution': 'clinical',
  'diagnosis-cancer-types': 'clinical',
  'cancer-excluded-reasons': 'clinical',
  'referral-routes': 'referrals',
  'referrals-by-cancer-type': 'referrals',
  'investigations-before-referral': 'referrals',
  'investigations-by-type': 'referrals',
  'safety-netting-recorded': 'referrals',
  'symptom-ppv-summary': 'symptoms',
  'symptom-ppv-by-symptom': 'symptoms',
  'symptom-ppv-by-symptom-cancer-type': 'symptoms',
  'symptom-ppv-sankey': 'symptoms',
  'consultation-count-distribution': 'consultations',
  'consultations-between-milestones': 'consultations',
  'place-of-presentation': 'consultations',
  'encounter-count': 'consultations',
  'outcome-distribution': 'outcomes',
  'avoidable-delays-summary': 'outcomes',
  'cancer-episode-count': 'pathways',
};

function inferFromTopic(topic: string): string | null {
  if (topic.includes('demograph')) return 'demographics';
  if (topic.includes('pathway') || topic.includes('interval')) return 'pathways';
  if (topic.includes('clinical') || topic.includes('comorbidit')) return 'clinical';
  if (topic.includes('referral') || topic.includes('investigation')) return 'referrals';
  if (topic.includes('symptom')) return 'symptoms';
  if (topic.includes('consult')) return 'consultations';
  if (topic.includes('outcome')) return 'outcomes';
  return null;
}

function inferFromText(text: string): string | null {
  if (text.includes('age') || text.includes('gender') || text.includes('ethnic') || text.includes('imd') || text.includes('pyramid') || text.includes('patient count')) return 'demographics';
  if (text.includes('pathway') || text.includes('interval') || text.includes('milestone')) return 'pathways';
  if (text.includes('comorbidit') || text.includes('charlson') || text.includes('stage') || text.includes('cancer type') || text.includes('diagnosis')) return 'clinical';
  if (text.includes('referral') || text.includes('investigation') || text.includes('safety')) return 'referrals';
  if (text.includes('symptom') || text.includes('ppv')) return 'symptoms';
  if (text.includes('consult') || text.includes('presentation')) return 'consultations';
  if (text.includes('outcome') || text.includes('delay') || text.includes('excluded')) return 'outcomes';
  return null;
}

export function inferCategory(measure: Measure): string {
  const id = measure.id || '';
  if (CATEGORY_MAP[id]) return CATEGORY_MAP[id];

  const topic = measure.topic?.[0]?.coding?.[0]?.code?.toLowerCase() || '';
  const topicResult = inferFromTopic(topic);
  if (topicResult) return topicResult;

  const text = `${id} ${measure.title || ''}`.toLowerCase();
  return inferFromText(text) || 'other';
}

export function getCategoryDef(key: string): MeasureCategory {
  return CATEGORIES.find((c) => c.key === key) || CATEGORIES[CATEGORIES.length - 1];
}
