/**
 * Minimal safe markdown-to-HTML renderer for SBAR stage bodies.
 *
 * Handles the subset of Markdown that the SBAR pipeline produces:
 *   - ATX headings (##, ###, ####)
 *   - Unordered lists (- or * at any indent level)
 *   - Paragraphs (blank-line delimited)
 *   - Inline: **bold**, _italic_, *italic*, ***bold-italic***
 *   - [RULE: ...] inline citations (stripped -- internal audit IDs
 *     are not meaningful to external consumers)
 *
 * No external dependencies. XSS-safe: raw text is HTML-escaped before
 * any inline pattern substitution so patterns can only EMIT known tags.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")
 */
const RULE_CITATION_RE = /\[RULE:\s*[^\]]+\]/g;
const HEADING_RE = /^(#{2,4})\s+(.+)$/;
const LIST_ITEM_RE = /^(\s*)[-*]\s+(.+)$/;

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMarkdown(raw: string): string {
  const s = escapeHtml(raw);
  return s
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/~~(.+?)~~/g, "<del>$1</del>")
    .replace(/_([^_\s][^_]*[^_\s]|[^_\s])_/g, "<em>$1</em>")
    .replace(/\*([^*\s][^*]*[^*\s]|[^*\s])\*/g, "<em>$1</em>");
}

interface Block {
  type: "heading" | "list" | "paragraph";
  level?: number;
  text?: string;
  items?: { indent: number; text: string }[];
}

function parseBlocks(md: string): Block[] {
  const stripped = md.replace(RULE_CITATION_RE, "").trim();
  const lines = stripped.split(/\r?\n/);

  const blocks: Block[] = [];
  let paraLines: string[] = [];
  let listItems: { indent: number; text: string }[] = [];

  function flushPara(): void {
    const joined = paraLines
      .map((l) => l.trim())
      .filter(Boolean)
      .join(" ");
    if (joined) blocks.push({ type: "paragraph", text: joined });
    paraLines = [];
  }

  function flushList(): void {
    if (listItems.length > 0) {
      blocks.push({ type: "list", items: listItems });
      listItems = [];
    }
  }

  for (const line of lines) {
    const trimmed = line.trim();

    if (!trimmed) {
      flushPara();
      flushList();
      continue;
    }

    const headingMatch = HEADING_RE.exec(trimmed);
    if (headingMatch) {
      flushPara();
      flushList();
      blocks.push({
        type: "heading",
        level: (headingMatch[1] ?? "##").length,
        text: headingMatch[2] ?? "",
      });
      continue;
    }

    const listMatch = LIST_ITEM_RE.exec(line);
    if (listMatch) {
      flushPara();
      const indent = (listMatch[1] ?? "").length;
      listItems.push({ indent, text: listMatch[2] ?? "" });
      continue;
    }

    flushList();
    paraLines.push(trimmed);
  }

  flushPara();
  flushList();
  return blocks;
}

function renderList(
  items: { indent: number; text: string }[],
  baseIndent: number,
  idx: { current: number },
): string {
  let html = '<ul class="leo-md-list">';
  while (idx.current < items.length) {
    // Guarded by while condition above -- non-null assertion is safe.
    const item = items[idx.current]!;
    if (item.indent < baseIndent) break;
    if (item.indent > baseIndent) {
      html += renderList(items, item.indent, idx);
      continue;
    }
    idx.current++;
    let li = `<li class="leo-md-item">${inlineMarkdown(item.text)}`;
    const next = items[idx.current];
    if (next !== undefined && next.indent > baseIndent) {
      li += renderList(items, next.indent, idx);
    }
    li += "</li>";
    html += li;
  }
  html += "</ul>";
  return html;
}

export function renderMarkdownToHtml(md: string): string {
  if (!md) return "";
  const blocks = parseBlocks(md);
  const parts: string[] = [];
  for (const block of blocks) {
    if (block.type === "heading") {
      const tag = `h${Math.min(block.level ?? 3, 6)}`;
      parts.push(
        `<${tag} class="leo-md-h">${inlineMarkdown(block.text ?? "")}</${tag}>`,
      );
    } else if (block.type === "list" && block.items && block.items.length > 0) {
      const baseIndent = block.items[0]!.indent;
      const idx = { current: 0 };
      parts.push(renderList(block.items, baseIndent, idx));
    } else if (block.type === "paragraph") {
      parts.push(`<p class="leo-md-p">${inlineMarkdown(block.text ?? "")}</p>`);
    }
  }
  return parts.join("\n");
}
