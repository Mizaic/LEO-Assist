/**
 * Widget-faithful HTML for SBAR PDF capture.
 *
 * Mirrors the leo-sbar stage cards, markdown renderer, and LEO chrome so
 * html2canvas produces a PDF that matches the on-screen widget.
 *
 * Atlas trace:
 *   DO: DO-598A4BB1
 *   DI: DI-15BC0C79
 *   Risks: R-7299F8D7
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-598A4BB1")
 */
import {
  STAGE_LABELS,
  STAGE_THEME,
  splitFinalSbar,
  stripSourceComments,
  type SbarStageName,
} from "@/components/sbar-final/SbarFinalView";

export const SBAR_PDF_ADVISORY =
  "AI-generated summary. Clinician review required before acting on this " +
  "content. This is a decision support aid, it does not replace your " +
  "clinical judgement.";

const FONT =
  '"Albert Sans", system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif';
const FONT_HEADING =
  '"Overpass", "Albert Sans", system-ui, -apple-system, Segoe UI, sans-serif';

const RING =
  "M106.508 20.9663C106.547 21.3824 106.577 22.1104 106.577 22.5378C106.577 29.8809 100.675 35.798 93.3446 35.798C86.0147 35.798 80.0722 29.8449 80.0722 22.5019C80.0722 15.1588 86.0147 9.20575 93.3446 9.20575C94.2281 9.20575 95.0889 9.29652 95.9232 9.46104L98.6623 0.601362C96.8992 0.156959 95.2437 0 93.3446 0C80.9406 0 70.8848 10.0738 70.8848 22.5C70.8848 34.9262 80.9406 45 93.3446 45C105.749 45 115.805 34.9262 115.805 22.5C115.805 21.3899 115.721 20.2988 115.567 19.2322L106.509 20.9644L106.508 20.9663Z";
const ACCENT =
  "M99.8359 10.9118C102.224 12.2564 104.051 14.3252 105.352 16.8763L114.383 14.5635C112.344 9.11531 108.385 4.87931 103.064 2.21289L99.8359 10.9118Z";

const RULE_TAG_RE = /\[RULE:\s*[^\]]+\]/g;
const HEADING_RE = /^(#{2,4})\s+(.+)$/;
const LIST_RE = /^(\s*)[-*]\s+(.+)$/;

type MdBlock =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: number; text: string }
  | { type: "list"; items: Array<{ indent: number; text: string }> };

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMarkdown(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/_([^_\s][^_]*[^_\s]|[^_\s])_/g, "<em>$1</em>")
    .replace(/\*([^*\s][^*]*[^*\s]|[^*\s])\*/g, "<em>$1</em>");
}

function parseMarkdownBlocks(md: string): MdBlock[] {
  const lines = md.replace(RULE_TAG_RE, "").trim().split(/\r?\n/);
  const out: MdBlock[] = [];
  let paragraph: string[] = [];
  let listItems: Array<{ indent: number; text: string }> = [];

  const flushParagraph = () => {
    const text = paragraph.map((l) => l.trim()).filter(Boolean).join(" ");
    if (text) out.push({ type: "paragraph", text });
    paragraph = [];
  };
  const flushList = () => {
    if (listItems.length) out.push({ type: "list", items: listItems });
    listItems = [];
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }
    const heading = HEADING_RE.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      out.push({
        type: "heading",
        level: (heading[1] ?? "##").length,
        text: heading[2] ?? "",
      });
      continue;
    }
    const list = LIST_RE.exec(line);
    if (list) {
      flushParagraph();
      listItems.push({ indent: (list[1] ?? "").length, text: list[2] ?? "" });
      continue;
    }
    flushList();
    paragraph.push(trimmed);
  }
  flushParagraph();
  flushList();
  return out;
}

function renderList(
  items: Array<{ indent: number; text: string }>,
  minIndent: number,
  cursor: { current: number },
): string {
  let html = '<ul class="leo-md-list">';
  while (cursor.current < items.length) {
    const item = items[cursor.current];
    if (item.indent < minIndent) break;
    if (item.indent > minIndent) {
      html += renderList(items, item.indent, cursor);
      continue;
    }
    cursor.current += 1;
    let li = `<li class="leo-md-item">${inlineMarkdown(item.text)}`;
    const next = items[cursor.current];
    if (next && next.indent > minIndent) {
      li += renderList(items, next.indent, cursor);
    }
    li += "</li>";
    html += li;
  }
  return `${html}</ul>`;
}

/** Convert a stage body markdown string to widget-style HTML. */
export function markdownBodyToHtml(md: string): string {
  if (!md) return "";
  const blocks = parseMarkdownBlocks(md);
  const parts: string[] = [];
  for (const block of blocks) {
    if (block.type === "heading") {
      const tag = `h${Math.min(block.level, 6)}`;
      parts.push(
        `<${tag} class="leo-md-h">${inlineMarkdown(block.text)}</${tag}>`,
      );
    } else if (block.type === "list" && block.items.length > 0) {
      const cursor = { current: 0 };
      parts.push(renderList(block.items, block.items[0].indent, cursor));
    } else if (block.type === "paragraph") {
      parts.push(`<p class="leo-md-p">${inlineMarkdown(block.text)}</p>`);
    }
  }
  return parts.join("\n");
}

function stageCss(stage: SbarStageName): string {
  const theme = STAGE_THEME[stage];
  return `
.leo-stage[data-stage="${stage}"] {
  border-left-color: ${theme.accent};
  background: ${theme.tint};
}
.leo-stage[data-stage="${stage}"] .leo-stage-header { color: ${theme.ink}; }
.leo-stage[data-stage="${stage}"] .leo-md-h { color: ${theme.ink}; }
`;
}

function exportStyles(): string {
  const stages = (Object.keys(STAGE_THEME) as SbarStageName[])
    .map(stageCss)
    .join("\n");
  return `
.leo-pdf-root {
  box-sizing: border-box;
  width: 720px;
  padding: 16px;
  font-family: ${FONT};
  color: #0f172a;
  background: #ffffff;
  line-height: 1.6;
  font-size: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
}
.leo-pdf-root *, .leo-pdf-root *::before, .leo-pdf-root *::after {
  box-sizing: border-box;
}
.leo-pdf-root strong, .leo-pdf-root b { font-weight: 700; }
.leo-pdf-root em, .leo-pdf-root i { font-style: italic; }
.leo-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 10px;
  margin-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
  color: #0d46d6;
}
.leo-mark {
  width: 26px;
  height: 26px;
  color: #00093b;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}
.leo-mark svg { display: block; width: 26px; height: 26px; }
.leo-product {
  font-family: ${FONT_HEADING};
  font-weight: 700;
  font-size: 13.5px;
  flex: 1;
}
.leo-advisory {
  border: 1px solid #0d46d6;
  background: #e8effc;
  color: #002178;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  margin-bottom: 10px;
}
.leo-stages { display: flex; flex-direction: column; gap: 10px; }
.leo-stage {
  border: 1px solid #e2e8f0;
  border-left-width: 4px;
  border-radius: 8px;
  overflow: hidden;
}
.leo-stage-header {
  padding: 7px 14px;
  font-family: ${FONT_HEADING};
  font-weight: 700;
  font-size: 12px;
  letter-spacing: 0.3px;
  text-transform: uppercase;
  background: transparent;
}
.leo-stage-body { padding: 6px 14px 12px; }
.leo-md-p { margin: 7px 0; font-size: 13px; line-height: 1.6; }
.leo-md-p:first-child { margin-top: 4px; }
.leo-md-p:last-child { margin-bottom: 2px; }
.leo-md-h {
  margin: 14px 0 5px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  text-transform: uppercase;
}
.leo-md-h:first-child { margin-top: 6px; }
.leo-md-list { margin: 6px 0; padding-left: 20px; list-style: disc; }
.leo-md-list .leo-md-list {
  margin: 3px 0;
  padding-left: 14px;
  list-style: circle;
}
.leo-md-list > .leo-md-item {
  margin: 6px 0;
  font-size: 13px;
  line-height: 1.55;
  color: #0f172a;
}
.leo-md-list .leo-md-list > .leo-md-item {
  margin: 3px 0;
  font-size: 12px;
  color: #475569;
  line-height: 1.5;
}
.leo-empty { color: #475569; font-size: 13px; padding: 8px 0; }
${stages}
`;
}

const LEO_MARK =
  '<span class="leo-mark" aria-hidden="true">' +
  '<svg viewBox="70.8848 0 44.9202 45" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="LEO by Mizaic">' +
  `<path d="${RING}" fill="currentColor"/>` +
  `<path d="${ACCENT}" fill="#d758ff"/>` +
  "</svg></span>";

function renderStage(stage: SbarStageName, body: string): string {
  const html = markdownBodyToHtml(stripSourceComments(body));
  return (
    `<section class="leo-stage" data-stage="${stage}" data-pdf-block="stage">` +
    `<header class="leo-stage-header">${STAGE_LABELS[stage]}</header>` +
    `<div class="leo-stage-body leo-stage-body--md">${html}</div>` +
    `</section>`
  );
}

/**
 * Build the off-screen DOM used for html2canvas capture.
 * Caller must append to document.body and remove after capture.
 * Elements marked data-pdf-block are page-break boundaries.
 */
export function buildSbarPdfCaptureRoot(markdown: string): HTMLElement {
  const sections = splitFinalSbar(stripSourceComments(markdown ?? ""));
  const stagesHtml =
    sections.length === 0
      ? '<div class="leo-empty" data-pdf-block="empty">No SBAR content yet.</div>'
      : sections.map((s) => renderStage(s.stage, s.body)).join("");

  const root = document.createElement("div");
  root.className = "leo-pdf-root";
  root.setAttribute("data-testid", "leo-sbar-pdf-capture");
  root.innerHTML = `
<style>${exportStyles()}</style>
<div data-pdf-block="chrome">
  <header class="leo-header">
    ${LEO_MARK}
    <span class="leo-product">LEO by Mizaic</span>
  </header>
  <div class="leo-advisory" role="alert">${escapeHtml(SBAR_PDF_ADVISORY)}</div>
</div>
<div class="leo-stages">${stagesHtml}</div>
`;
  return root;
}
