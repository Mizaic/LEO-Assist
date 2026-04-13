const TRIGGER_OPTIONS_RAW = [
  { id: "encounter-created", label: "New Encounter Created", description: "Fires when a new GP encounter document is ingested." },
  { id: "referral-received", label: "Referral Received", description: "Fires when a referral letter is uploaded or received via integration." },
  { id: "training-run-requested", label: "Training Run Requested", description: "Manual trigger — used to generate gold-standard NER training data." },
  { id: "results-received", label: "Investigation Results Received", description: "Fires when lab results or diagnostic reports arrive." },
  { id: "safety-net-check", label: "Safety Net Timer", description: "Scheduled check for overdue investigations and follow-ups." },
  { id: "manual", label: "Manual / API Call", description: "Pipeline is invoked manually via the API or admin UI." },
] as const;

export const TRIGGER_OPTIONS = [...TRIGGER_OPTIONS_RAW].sort((a, b) =>
  a.label.localeCompare(b.label, "en", { sensitivity: "base" }),
);

