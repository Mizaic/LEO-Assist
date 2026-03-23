"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import Placeholder from "@tiptap/extension-placeholder";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import { Markdown } from "tiptap-markdown";
import type { Editor } from "@tiptap/core";
import Toolbar from "./Toolbar";
import "./MarkdownEditor.css";

export type EditorMode = "create" | "edit" | "view";

export interface MarkdownEditorHandle {
  getMarkdown(): string;
  setMarkdown(md: string): void;
  setMode(mode: EditorMode): void;
}

export interface MarkdownEditorProps {
  initialContent?: string;
  mode?: EditorMode;
  onChange?: (markdown: string) => void;
  placeholder?: string;
  className?: string;
  autoFocus?: boolean;
  minHeight?: number | string;
}

const MarkdownEditor = forwardRef<MarkdownEditorHandle, MarkdownEditorProps>(
  (
    {
      initialContent = "",
      mode: initialMode = "edit",
      onChange,
      placeholder = "Start writing your prompt here…",
      className,
      autoFocus = false,
      minHeight = 260,
    },
    ref,
  ) => {
    const [mode, setModeState] = useState<EditorMode>(initialMode);
    const onChangeRef = useRef(onChange);
    onChangeRef.current = onChange;
    const readMarkdown = useCallback((storage: unknown): string => {
      const markdown = (storage as { markdown?: { getMarkdown?: () => string } }).markdown;
      return typeof markdown?.getMarkdown === "function" ? markdown.getMarkdown() : "";
    }, []);

    const editor = useEditor({
      immediatelyRender: false,
      extensions: [
        StarterKit.configure({ codeBlock: { languageClassPrefix: "language-" } }),
        Underline,
        Link.configure({ openOnClick: false }),
        Table.configure({ resizable: false }),
        TableRow,
        TableHeader,
        TableCell,
        TaskList,
        TaskItem.configure({ nested: false }),
        Placeholder.configure({ placeholder }),
        Markdown.configure({
          html: false,
          tightLists: true,
          tightListClass: "tight",
          bulletListMarker: "-",
          linkify: false,
          breaks: false,
          transformPastedText: true,
          transformCopiedText: false,
        }),
      ],
      content: initialContent ? { type: "doc" } : "",
      editable: mode !== "view",
      autofocus: autoFocus,
      onUpdate({ editor: ed }) {
        const md = readMarkdown(ed.storage);
        onChangeRef.current?.(md);
      },
    });

    // Load initial markdown content once the editor is ready
    useEffect(() => {
      if (!editor || !initialContent) return;
      // Commands aren't available immediately after construction; defer one tick
      const t = setTimeout(() => {
        if (editor.isDestroyed) return;
        editor.commands.setContent(initialContent);
      }, 0);
      return () => clearTimeout(t);
      // intentionally run only once on mount
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editor]);

    // Sync editable when mode changes
    useEffect(() => {
      if (!editor) return;
      editor.setEditable(mode !== "view");
    }, [editor, mode]);

    const getMarkdown = useCallback((): string => {
      if (!editor) return "";
      return readMarkdown(editor.storage);
    }, [editor, readMarkdown]);

    const setMarkdown = useCallback(
      (md: string) => {
        editor?.commands.setContent(md);
      },
      [editor],
    );

    const setMode = useCallback((m: EditorMode) => setModeState(m), []);

    useImperativeHandle(ref, () => ({ getMarkdown, setMarkdown, setMode }), [
      getMarkdown,
      setMarkdown,
      setMode,
    ]);

    return (
      <div
        className={[
          "md-editor",
          mode === "view" ? "md-editor--view" : "md-editor--edit",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {mode !== "view" && editor && <Toolbar editor={editor} />}
        <EditorContent
          editor={editor}
          style={{ minHeight: typeof minHeight === "number" ? `${minHeight}px` : minHeight }}
        />
      </div>
    );
  },
);

MarkdownEditor.displayName = "MarkdownEditor";
export default MarkdownEditor;

// Re-export editor type for consumers
export type { Editor };
