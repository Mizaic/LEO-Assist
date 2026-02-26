export interface Resource {
  resourceType: string;
  id?: string;
  meta?: Meta;
}

export interface Meta {
  versionId?: string;
  lastUpdated?: string;
}

export interface Coding {
  system?: string;
  code?: string;
  display?: string;
}

export interface CodeableConcept {
  coding?: Coding[];
  text?: string;
}

export interface Reference {
  reference?: string;
  display?: string;
}

export interface Period {
  start?: string;
  end?: string;
}

export interface Attachment {
  contentType?: string;
  data?: string;
  url?: string;
  title?: string;
}

export interface Extension {
  url: string;
  valueString?: string;
  valueAttachment?: Attachment;
}

export interface BenchmarkConfig {
  benchmarkSetId?: string;
  metricMapping?: Array<{ measureOutput?: string; benchmarkMetricId?: string }>;
}

export interface Measure extends Resource {
  resourceType: 'Measure';
  url?: string;
  name?: string;
  title?: string;
  status: 'draft' | 'active' | 'retired' | 'unknown';
  description?: string;
  library?: string[];
  topic?: CodeableConcept[];
  group?: MeasureGroup[];
  benchmarkConfig?: BenchmarkConfig;
}

export interface MeasureGroup {
  code?: CodeableConcept;
  description?: string;
  population?: MeasurePopulation[];
  stratifier?: MeasureStratifier[];
}

export interface MeasurePopulation {
  code?: CodeableConcept;
  criteria?: {
    language?: string;
    expression?: string;
  };
}

export interface MeasureStratifier {
  code?: CodeableConcept;
  criteria?: {
    language?: string;
    expression?: string;
  };
}

export interface Library extends Resource {
  resourceType: 'Library';
  url?: string;
  name?: string;
  title?: string;
  status: 'draft' | 'active' | 'retired' | 'unknown';
  type?: CodeableConcept;
  content?: Attachment[];
}

export interface MeasureReport extends Resource {
  resourceType: 'MeasureReport';
  status: 'complete' | 'pending' | 'error';
  type: 'individual' | 'subject-list' | 'summary' | 'data-collection';
  measure: string;
  subject?: Reference;
  date?: string;
  period: Period;
  group?: MeasureReportGroup[];
  extension?: Extension[];
}

export interface MeasureReportGroup {
  code?: CodeableConcept;
  population?: MeasureReportPopulation[];
  measureScore?: { value?: number };
  stratifier?: MeasureReportStratifier[];
}

export interface MeasureReportPopulation {
  code?: CodeableConcept;
  count?: number;
}

export interface MeasureReportStratifier {
  code?: CodeableConcept[];
  stratum?: MeasureReportStratum[];
}

export interface MeasureReportStratum {
  value?: CodeableConcept;
  population?: MeasureReportPopulation[];
  measureScore?: { value?: number };
}

export interface DocumentReference extends Resource {
  resourceType: 'DocumentReference';
  status: 'current' | 'superseded' | 'entered-in-error';
  type?: CodeableConcept;
  subject?: Reference;
  date?: string;
  content: DocumentReferenceContent[];
  context?: { related?: Reference[] };
}

export interface DocumentReferenceContent {
  attachment: Attachment;
  format?: Coding;
}

export interface Organization extends Resource {
  resourceType: 'Organization';
  name?: string;
}

export interface Patient extends Resource {
  resourceType: 'Patient';
  name?: Array<{
    text?: string;
    given?: string[];
    family?: string;
  }>;
}

export interface Bundle<T extends Resource = Resource> extends Resource {
  resourceType: 'Bundle';
  type: 'searchset' | 'batch' | 'transaction' | 'collection';
  total?: number;
  entry?: BundleEntry<T>[];
}

export interface BundleEntry<T extends Resource = Resource> {
  resource?: T;
  fullUrl?: string;
}

export interface OperationOutcome extends Resource {
  resourceType: 'OperationOutcome';
  issue: OperationOutcomeIssue[];
}

export interface OperationOutcomeIssue {
  severity: 'fatal' | 'error' | 'warning' | 'information';
  code: string;
  details?: CodeableConcept;
  diagnostics?: string;
}
