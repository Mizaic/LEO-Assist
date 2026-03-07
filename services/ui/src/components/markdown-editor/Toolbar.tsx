"use client";

import React, { useCallback } from "react";
import type { Editor } from "@tiptap/core";
import Tooltip from "@mui/material/Tooltip";
import IconButton from "@mui/material/IconButton";
import Divider from "@mui/material/Divider";
import Box from "@mui/material/Box";

// MUI icons
import FormatBoldIcon from "@mui/icons-material/FormatBold";
import FormatItalicIcon from "@mui/icons-material/FormatItalic";
import FormatUnderlinedIcon from "@mui/icons-material/FormatUnderlined";
import FormatStrikethroughIcon from "@mui/icons-material/FormatStrikethrough";
import FormatListBulletedIcon from "@mui/icons-material/FormatListBulleted";
import FormatListNumberedIcon from "@mui/icons-material/FormatListNumbered";
import CheckBoxOutlinedIcon from "@mui/icons-material/CheckBoxOutlined";
import FormatQuoteIcon from "@mui/icons-material/FormatQuote";
import CodeIcon from "@mui/icons-material/Code";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";
import HorizontalRuleIcon from "@mui/icons-material/HorizontalRule";
import UndoIcon from "@mui/icons-material/Undo";
import RedoIcon from "@mui/icons-material/Redo";

interface ToolbarProps {
  editor: Editor;
}

interface ToolbarButtonProps {
  label: string;
  shortcut?: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function ToolbarButton({
  label,
  shortcut,
  active = false,
  disabled = false,
  onClick,
  children,
}: ToolbarButtonProps) {
  const title = shortcut ? `${label} (${shortcut})` : label;
  return (
    <Tooltip title={title} placement="top" arrow>
      <span>
        <IconButton
          size="small"
          onClick={onClick}
          disabled={disabled}
          aria-label={label}
          sx={{
            borderRadius: 1,
            color: active ? "primary.main" : "text.secondary",
            bgcolor: active ? "primary.50" : "transparent",
            "&:hover": { bgcolor: active ? "primary.100" : "action.hover" },
            width: 30,
            height: 30,
          }}
        >
          {children}
        </IconButton>
      </span>
    </Tooltip>
  );
}

function HeadingButton({ editor, level }: { editor: Editor; level: 1 | 2 | 3 }) {
  const label = `Heading ${level}`;
  const shortcut = `Ctrl+Alt+${level}`;
  return (
    <ToolbarButton
      label={label}
      shortcut={shortcut}
      active={editor.isActive("heading", { level })}
      onClick={() => editor.chain().focus().toggleHeading({ level }).run()}
    >
      <Box
        component="span"
        sx={{ fontWeight: 700, fontSize: level === 1 ? "0.85rem" : level === 2 ? "0.8rem" : "0.75rem" }}
      >
        H{level}
      </Box>
    </ToolbarButton>
  );
}

export default function Toolbar({ editor }: ToolbarProps) {
  const insertTable = useCallback(() => {
    editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
  }, [editor]);

  return (
    <Box
      sx={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 0.25,
        px: 1,
        py: 0.5,
        borderBottom: "1px solid",
        borderColor: "divider",
        bgcolor: "grey.50",
        borderRadius: "6px 6px 0 0",
      }}
    >
      {/* Text format */}
      <ToolbarButton label="Bold" shortcut="Ctrl+B" active={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}>
        <FormatBoldIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Italic" shortcut="Ctrl+I" active={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}>
        <FormatItalicIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Underline" shortcut="Ctrl+U" active={editor.isActive("underline")}
        onClick={() => editor.chain().focus().toggleUnderline().run()}>
        <FormatUnderlinedIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Strikethrough" shortcut="Ctrl+Shift+X" active={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}>
        <FormatStrikethroughIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>

      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

      {/* Headings */}
      <HeadingButton editor={editor} level={1} />
      <HeadingButton editor={editor} level={2} />
      <HeadingButton editor={editor} level={3} />

      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

      {/* Lists */}
      <ToolbarButton label="Bullet list" active={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}>
        <FormatListBulletedIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Numbered list" active={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        <FormatListNumberedIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Checklist" active={editor.isActive("taskList")}
        onClick={() => editor.chain().focus().toggleTaskList().run()}>
        <CheckBoxOutlinedIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Quote" active={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}>
        <FormatQuoteIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>

      <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

      {/* Code / table / rule */}
      <ToolbarButton label="Inline code" shortcut="Ctrl+E" active={editor.isActive("code")}
        onClick={() => editor.chain().focus().toggleCode().run()}>
        <CodeIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Insert table" onClick={insertTable}>
        <TableChartOutlinedIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Horizontal rule"
        onClick={() => editor.chain().focus().setHorizontalRule().run()}>
        <HorizontalRuleIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>

      <Box sx={{ flex: 1 }} />

      {/* Undo / redo */}
      <ToolbarButton label="Undo" shortcut="Ctrl+Z"
        disabled={!editor.can().undo()}
        onClick={() => editor.chain().focus().undo().run()}>
        <UndoIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
      <ToolbarButton label="Redo" shortcut="Ctrl+Y"
        disabled={!editor.can().redo()}
        onClick={() => editor.chain().focus().redo().run()}>
        <RedoIcon sx={{ fontSize: 18 }} />
      </ToolbarButton>
    </Box>
  );
}
