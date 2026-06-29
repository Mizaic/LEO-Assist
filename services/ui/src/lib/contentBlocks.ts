/**
 * Content block catalogue for the audit template builder.
 *
 * Content blocks are non-data tiles (headings, text, dividers, callouts,
 * images, links). They are stored as AuditTile with:
 *   tile_type: "text"
 *   metric_id: the block_id (e.g. "content-heading")
 *   param_overrides: the block's editable content
 *
 * Atlas trace: DO-A9863AB6 / DI-64CA7740
 */

export interface ContentBlockEntry {
  block_id: string;
  label: string;
  description: string;
  colour: string;
  group: "text" | "layout" | "media" | "data";
  defaultLayout: { w: number; h: number };
  defaultParams: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Catalogue
// ---------------------------------------------------------------------------

export const CONTENT_CATALOGUE: ContentBlockEntry[] = [
  // -- Text group -----------------------------------------------------------
  {
    block_id: "content-heading",
    label: "Heading",
    description: "Large section title",
    colour: "#1E293B",
    group: "text",
    defaultLayout: { w: 12, h: 2 },
    defaultParams: { text: "Section heading", level: "h2", align: "left" },
  },
  {
    block_id: "content-subheading",
    label: "Subheading",
    description: "Smaller section header",
    colour: "#475569",
    group: "text",
    defaultLayout: { w: 12, h: 2 },
    defaultParams: { text: "Subheading text", level: "h3", align: "left" },
  },
  {
    block_id: "content-body",
    label: "Text block",
    description: "Paragraph notes or narrative",
    colour: "#64748B",
    group: "text",
    defaultLayout: { w: 6, h: 3 },
    defaultParams: { text: "Add your narrative text here.", align: "left" },
  },
  {
    block_id: "content-callout",
    label: "Callout",
    description: "Highlighted insight or info box",
    colour: "#0284C7",
    group: "text",
    defaultLayout: { w: 6, h: 2 },
    defaultParams: {
      text: "Key insight or finding.",
      accentColour: "#0284C7",
      icon: "info",
    },
  },
  {
    block_id: "content-label",
    label: "Label / tag",
    description: "Small inline badge or category label",
    colour: "#7C3AED",
    group: "text",
    defaultLayout: { w: 3, h: 1 },
    defaultParams: { text: "DRAFT", bgColour: "#EDE9FE", textColour: "#7C3AED" },
  },
  // -- Layout group ---------------------------------------------------------
  {
    block_id: "content-divider",
    label: "Divider",
    description: "Horizontal separator line",
    colour: "#CBD5E1",
    group: "layout",
    defaultLayout: { w: 12, h: 1 },
    defaultParams: { style: "solid", colour: "#E2E8F0", thickness: 1 },
  },
  {
    block_id: "content-spacer",
    label: "Spacer",
    description: "Blank space between sections",
    colour: "#F1F5F9",
    group: "layout",
    defaultLayout: { w: 12, h: 1 },
    defaultParams: {},
  },
  {
    block_id: "content-banner",
    label: "Banner",
    description: "Full-width colored section header",
    colour: "#1E40AF",
    group: "layout",
    defaultLayout: { w: 12, h: 2 },
    defaultParams: {
      text: "Report section",
      bgColour: "#1E40AF",
      textColour: "#FFFFFF",
      subtitle: "",
    },
  },
  // -- Media group ----------------------------------------------------------
  {
    block_id: "content-image",
    label: "Image",
    description: "Image or logo placeholder",
    colour: "#7C3AED",
    group: "media",
    defaultLayout: { w: 4, h: 4 },
    defaultParams: { url: "", alt: "", caption: "" },
  },
  {
    block_id: "content-link",
    label: "Link / button",
    description: "Clickable link or action button",
    colour: "#0369A1",
    group: "media",
    defaultLayout: { w: 3, h: 2 },
    defaultParams: { text: "View full report", url: "#", variant: "button" },
  },
  // -- Data group -----------------------------------------------------------
  {
    block_id: "content-metric-card",
    label: "Metric card",
    description: "Standalone KPI number (manual value)",
    colour: "#047857",
    group: "data",
    defaultLayout: { w: 3, h: 3 },
    defaultParams: {
      value: "--",
      label: "Metric name",
      subtitle: "Period: this month",
      colour: "#047857",
      delta: "",
    },
  },
];

export const CONTENT_GROUPS: Array<{
  id: ContentBlockEntry["group"];
  label: string;
}> = [
  { id: "text", label: "Text" },
  { id: "layout", label: "Layout" },
  { id: "media", label: "Media" },
  { id: "data", label: "Data" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function isContentBlock(metricId: string): boolean {
  return metricId.startsWith("content-");
}

export function getContentBlock(blockId: string): ContentBlockEntry | undefined {
  return CONTENT_CATALOGUE.find((b) => b.block_id === blockId);
}
