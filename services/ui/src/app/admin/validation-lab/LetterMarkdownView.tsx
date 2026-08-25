/**
 * Render clinical letter markdown with stage fact highlights.
 *
 * Atlas: DI-C953EF73 / DO-4FD76836 / VT-F0A6B9F4
 *
 * Atlas trace:
 *   DO: DO-4FD76836
 *   DI: DI-C953EF73
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4FD76836")
 */
"use client";

import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";

import { LetterMarks, MentionClockProvider } from "./LetterMarks";
import type { LetterMark } from "./letterHighlight";
import {
  parseLetterMarkdown,
  splitLetterSource,
  type BlockNode,
  type InlineNode,
} from "./letterMarkdown";

interface Props {
  text: string;
  marks?: LetterMark[];
  testId?: string;
  emptyLabel: string;
  focusTerm?: string;
}

export default function LetterMarkdownView({
  text,
  marks = [],
  testId,
  emptyLabel,
  focusTerm,
}: Props): ReactNode {
  if (!text.trim()) {
    return (
      <Typography variant="body2" color="text.secondary">
        {emptyLabel}
      </Typography>
    );
  }
  const { filename, body } = splitLetterSource(text);
  const blocks = parseLetterMarkdown(body || text);
  const letter = (
    <Box data-testid="validation-lab-letter-markdown" sx={MARKDOWN_SX}>
      {filename ? (
        <Chip
          size="small"
          variant="outlined"
          label={filename}
          data-testid="validation-lab-letter-filename"
          sx={{ mb: 1.5, maxWidth: "100%", height: "auto", py: 0.5 }}
        />
      ) : null}
      {blocks.map((block, index) => (
        <BlockView
          key={`${block.type}-${index}`}
          block={block}
          marks={marks}
          testId={testId}
          numberMentions={Boolean(focusTerm)}
        />
      ))}
    </Box>
  );
  if (!focusTerm) return letter;
  return (
    <MentionClockProvider resetKey={`${focusTerm}:${text.length}`}>
      {letter}
    </MentionClockProvider>
  );
}

function BlockView({
  block,
  marks,
  testId,
  numberMentions,
}: {
  block: BlockNode;
  marks: LetterMark[];
  testId?: string;
  numberMentions?: boolean;
}): ReactNode {
  if (block.type === "heading") {
    const variant = block.level === 1 ? "h5" : block.level === 2 ? "h6" : "subtitle1";
    return (
      <Typography variant={variant} component={`h${block.level}`} sx={{ fontWeight: 700 }}>
        <InlineView
          nodes={block.children}
          marks={marks}
          testId={testId}
          numberMentions={numberMentions}
        />
      </Typography>
    );
  }
  if (block.type === "hr") return <Box component="hr" />;
  if (block.type === "list") {
    const ListTag = block.ordered ? "ol" : "ul";
    return (
      <Box component={ListTag}>
        {block.items.map((item, index) => (
          <li key={`li-${index}`}>
            <InlineView
              nodes={item}
              marks={marks}
              testId={testId}
              numberMentions={numberMentions}
            />
          </li>
        ))}
      </Box>
    );
  }
  if (block.type === "table") {
    return (
      <TableView
        block={block}
        marks={marks}
        testId={testId}
        numberMentions={numberMentions}
      />
    );
  }
  return (
    <Typography variant="body2" component="p">
      {block.lines.map((line, index) => (
        <Box component="span" key={`ln-${index}`}>
          {index > 0 ? <br /> : null}
          <InlineView
            nodes={line}
            marks={marks}
            testId={testId}
            numberMentions={numberMentions}
          />
        </Box>
      ))}
    </Typography>
  );
}

function TableView({
  block,
  marks,
  testId,
  numberMentions,
}: {
  block: Extract<BlockNode, { type: "table" }>;
  marks: LetterMark[];
  testId?: string;
  numberMentions?: boolean;
}): ReactNode {
  return (
    <Box component="table">
      <thead>
        <tr>
          {block.header.map((cell, index) => (
            <Box component="th" scope="col" key={`th-${index}`}>
              <InlineView
                nodes={cell}
                marks={marks}
                testId={testId}
                numberMentions={numberMentions}
              />
            </Box>
          ))}
        </tr>
      </thead>
      <tbody>
        {block.rows.map((row, rowIndex) => (
          <tr key={`tr-${rowIndex}`}>
            {row.map((cell, cellIndex) => (
              <Box component="td" key={`td-${rowIndex}-${cellIndex}`}>
                <InlineView
                  nodes={cell}
                  marks={marks}
                  testId={testId}
                  numberMentions={numberMentions}
                />
              </Box>
            ))}
          </tr>
        ))}
      </tbody>
    </Box>
  );
}

function InlineView({
  nodes,
  marks,
  testId,
  numberMentions,
}: {
  nodes: InlineNode[];
  marks: LetterMark[];
  testId?: string;
  numberMentions?: boolean;
}): ReactNode {
  return nodes.map((node, index) => {
    if (node.type === "text") {
      return (
        <LetterMarks
          key={`tx-${index}`}
          text={node.value}
          marks={marks}
          testId={testId}
          numberMentions={numberMentions}
        />
      );
    }
    if (node.type === "code") {
      return <Box component="code" key={`cd-${index}`}>{node.value}</Box>;
    }
    const Tag = node.type === "strong" ? "strong" : "em";
    return (
      <Box component={Tag} key={`${node.type}-${index}`}>
        <InlineView
          nodes={node.children}
          marks={marks}
          testId={testId}
          numberMentions={numberMentions}
        />
      </Box>
    );
  });
}

const MARKDOWN_SX = {
  "& h1, & h2, & h3": { fontWeight: 700, mt: 1.5, mb: 0.75, lineHeight: 1.35 },
  "& h1": { fontSize: "1.25rem" },
  "& h2": { fontSize: "1.1rem" },
  "& h3": { fontSize: "1rem" },
  "& p": { my: 0.75, lineHeight: 1.65 },
  "& table": {
    borderCollapse: "collapse",
    width: "100%",
    my: 1.25,
    fontSize: "0.85rem",
  },
  "& th, & td": {
    border: "1px solid #D0D0D0",
    px: 1.25,
    py: 0.75,
    textAlign: "left",
    verticalAlign: "top",
  },
  "& th": { bgcolor: "#F5F5F5", fontWeight: 600 },
  "& tr:nth-of-type(even) td": { bgcolor: "#FAFAFA" },
  "& ul, & ol": { pl: 2.5, my: 0.75 },
  "& li": { mb: 0.25 },
  "& hr": { border: "none", borderTop: "2px solid #E0E0E0", my: 1.5 },
  "& strong": { fontWeight: 700 },
  "& code": {
    fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    fontSize: "0.85em",
    bgcolor: "#F3F3F3",
    px: 0.5,
    borderRadius: "3px",
  },
} as const;
