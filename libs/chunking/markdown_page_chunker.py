"""Markdown chunker ported from HCCP-Agents.

Atlas trace:
  DO: DO-58BD2EA0
  DI: DI-ACA9659D
  Look up via: get_design_control(dc_type="design-output", dc_id="DO-58BD2EA0")

Source: HCCP-Agents/agent/leo_agents/utils/markdown_page_chunker.py

langchain is not a LEO-AI-CORE dependency. Document objects are a
local dataclass with the same ``page_content`` / ``metadata`` fields
the HCCP-Agents callers used.

Only the table-preserving path is ported. That is the path
``chunk_markdown_text`` calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkDocument:
    """Stand-in for langchain_core.documents.Document."""

    page_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class MarkdownPageChunker:
    """Split markdown while keeping table blocks intact."""

    def __init__(self, markdown_text: str) -> None:
        self.markdown_text = markdown_text

    def _split_into_blocks(self) -> list[tuple[str, list[str]]]:
        """Split markdown into alternating text and table blocks."""
        lines = self.markdown_text.splitlines(keepends=True)
        blocks: list[tuple[str, list[str]]] = []
        buf: list[str] = []
        mode: str | None = None

        def flush() -> None:
            if buf and mode is not None:
                blocks.append((mode, buf.copy()))
            buf.clear()

        for line in lines:
            is_table_line = "|" in line
            if mode == "text" and is_table_line:
                flush()
                mode = "table"
            elif mode == "table" and not is_table_line:
                flush()
                mode = "text"
            elif mode is None:
                mode = "table" if is_table_line else "text"
            buf.append(line)
        flush()
        return blocks

    def extract_chunks_preserving_tables(
        self,
        target_size: int = 1000,
        source: str = "table_preserved_chunk",
        max_table_rows: int = 3,
    ) -> list[ChunkDocument]:
        """Combine blocks until target_size, then start a new chunk.

        ``max_table_rows`` is kept for call-site compatibility with the
        HCCP-Agents original. The original method does not use it.
        """
        del max_table_rows
        documents: list[ChunkDocument] = []
        idx = 0
        current = ""
        current_has_table = False

        for mode, lines in self._split_into_blocks():
            for block in self._sized_blocks("".join(lines).strip(), target_size):
                if current and len(current) + len(block) + 2 > target_size:
                    documents.append(self._doc(current, idx, source, current_has_table))
                    idx += 1
                    current = block
                    current_has_table = mode == "table"
                    continue
                current = f"{current}\n\n{block}" if current else block
                if mode == "table":
                    current_has_table = True

        if current:
            documents.append(self._doc(current, idx, source, current_has_table))
        return documents

    def _sized_blocks(self, text: str, target_size: int) -> list[str]:
        """Split one block when it is already larger than target_size."""
        if not text:
            return []
        if len(text) <= target_size:
            return [text]
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        packed: list[str] = []
        current = ""
        for part in parts:
            if current and len(current) + len(part) + 2 > target_size:
                packed.append(current)
                current = part
            elif current:
                current = f"{current}\n\n{part}"
            else:
                current = part
        if current:
            packed.append(current)
        return packed

    def _doc(
        self,
        text: str,
        idx: int,
        source: str,
        has_table: bool,
    ) -> ChunkDocument:
        cleaned = text.strip()
        return ChunkDocument(
            page_content=cleaned,
            metadata={
                "chunk_index": idx,
                "source": source,
                "chunk_length": len(cleaned),
                "contains_table": has_table,
            },
        )
