/**
 * Parse clinical letter markdown for Validation Lab run review.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 *
 * Atlas trace:
 *   DO: DO-4FD76836
 *   DI: DI-C953EF73
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4FD76836")
 */

import {
  extractSourceFilename,
  stripDocumentHeader,
} from "@/components/patients/documentFormat";

export type InlineNode =
  | { type: "text"; value: string }
  | { type: "strong"; children: InlineNode[] }
  | { type: "em"; children: InlineNode[] }
  | { type: "code"; value: string };

export type BlockNode =
  | { type: "heading"; level: 1 | 2 | 3; children: InlineNode[] }
  | { type: "paragraph"; lines: InlineNode[][] }
  | { type: "list"; ordered: boolean; items: InlineNode[][] }
  | { type: "table"; header: InlineNode[][]; rows: InlineNode[][][] }
  | { type: "hr" };

export function splitLetterSource(raw: string): {
  filename: string | null;
  body: string;
} {
  const text = String(raw || "");
  return {
    filename: extractSourceFilename(text),
    body: stripDocumentHeader(text),
  };
}

export function parseLetterMarkdown(md: string): BlockNode[] {
  const lines = String(md || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: BlockNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const consumed = consumeBlock(lines, index);
    if (consumed.block) blocks.push(consumed.block);
    index = consumed.next;
  }
  return blocks;
}

function consumeBlock(
  lines: string[],
  start: number,
): { block: BlockNode | null; next: number } {
  const line = lines[start] ?? "";
  if (!line.trim()) return { block: null, next: start + 1 };
  if (isHr(line)) return { block: { type: "hr" }, next: start + 1 };
  const heading = parseHeading(line);
  if (heading) return { block: heading, next: start + 1 };
  const table = tryParseTable(lines, start);
  if (table) return table;
  const list = tryParseList(lines, start);
  if (list) return list;
  return consumeParagraph(lines, start);
}

function parseHeading(line: string): BlockNode | null {
  const match = /^(#{1,3})\s+(.+)$/.exec(line.trim());
  if (!match) return null;
  const marks = match[1] ?? "#";
  const level = marks.length as 1 | 2 | 3;
  return { type: "heading", level, children: parseInline(match[2] ?? "") };
}

function consumeParagraph(
  lines: string[],
  start: number,
): { block: BlockNode; next: number } {
  const collected: string[] = [];
  let index = start;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (!line.trim()) break;
    if (isBlockBoundary(lines, index)) break;
    collected.push(line.trim());
    index += 1;
  }
  return {
    block: { type: "paragraph", lines: collected.map((row) => parseInline(row)) },
    next: index,
  };
}

function tryParseTable(
  lines: string[],
  start: number,
): { block: BlockNode; next: number } | null {
  if (!isTableStart(lines, start)) return null;
  const header = splitCells(lines[start] ?? "").map((cell) => parseInline(cell));
  const rows: InlineNode[][][] = [];
  let index = start + 2;
  while (index < lines.length && isTableRow(lines[index] ?? "")) {
    if (isTableSeparator(lines[index] ?? "")) break;
    rows.push(splitCells(lines[index] ?? "").map((cell) => parseInline(cell)));
    index += 1;
  }
  return { block: { type: "table", header, rows }, next: index };
}

function tryParseList(
  lines: string[],
  start: number,
): { block: BlockNode; next: number } | null {
  if (!isListItem(lines[start] ?? "")) return null;
  const ordered = /^\s*\d+\.\s+/.test(lines[start] ?? "");
  const items: InlineNode[][] = [];
  let index = start;
  while (index < lines.length && isListItem(lines[index] ?? "")) {
    const text = (lines[index] ?? "").replace(/^\s*(?:[-*]|\d+\.)\s+/, "");
    items.push(parseInline(text));
    index += 1;
  }
  return { block: { type: "list", ordered, items }, next: index };
}

function isBlockBoundary(lines: string[], index: number): boolean {
  const line = lines[index] ?? "";
  return isHr(line) || Boolean(parseHeading(line)) || isListItem(line) || isTableStart(lines, index);
}

function isHr(line: string): boolean {
  return /^(?:-{3,}|\*{3,})$/.test(line.trim());
}

function isListItem(line: string): boolean {
  return /^\s*(?:[-*]|\d+\.)\s+\S/.test(line);
}

function isTableStart(lines: string[], index: number): boolean {
  return isTableRow(lines[index] ?? "") && isTableSeparator(lines[index + 1] ?? "");
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("|") && trimmed.length > 1;
}

function isTableSeparator(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes("|") || !trimmed.includes("---")) return false;
  return /^[\s:|\-]+$/.test(trimmed);
}

function splitCells(line: string): string[] {
  const trimmed = line.trim();
  const inner = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const body = inner.endsWith("|") ? inner.slice(0, -1) : inner;
  return body.split("|").map((cell) => cell.trim());
}

export function parseInline(text: string): InlineNode[] {
  const out: InlineNode[] = [];
  const pattern = /\*\*(.+?)\*\*|`([^`]+)`|\*([^*\n]+)\*/g;
  let last = 0;
  let match = pattern.exec(text);
  while (match) {
    if (match.index > last) {
      out.push({ type: "text", value: text.slice(last, match.index) });
    }
    pushInlineMatch(out, match);
    last = match.index + match[0].length;
    match = pattern.exec(text);
  }
  if (last < text.length) out.push({ type: "text", value: text.slice(last) });
  return out.length ? out : [{ type: "text", value: text }];
}

function pushInlineMatch(out: InlineNode[], match: RegExpExecArray): void {
  if (match[1] != null) {
    out.push({ type: "strong", children: parseInline(match[1]) });
    return;
  }
  if (match[2] != null) {
    out.push({ type: "code", value: match[2] });
    return;
  }
  out.push({ type: "em", children: [{ type: "text", value: match[3] ?? "" }] });
}
