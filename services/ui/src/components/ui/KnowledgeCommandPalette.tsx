"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Modal from "@mui/material/Modal";
import Box from "@mui/material/Box";
import InputBase from "@mui/material/InputBase";
import Divider from "@mui/material/Divider";
import SearchIcon from "@mui/icons-material/Search";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import type { KnowledgeTabKey } from "@/lib/knowledgeCopy";

interface CommandResult {
  id: string;
  label: string;
  meta?: string;
  type: "domain" | "guideline" | "prompt" | "surface-form";
  tab: KnowledgeTabKey;
  icon: React.ReactNode;
}

const TYPE_LABELS: Record<CommandResult["type"], string> = {
  domain: "Domain",
  guideline: "Guideline",
  prompt: "AI Instructions",
  "surface-form": "Surface Form",
};

interface KnowledgeCommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onNavigate: (tab: KnowledgeTabKey) => void;
}

function ResultRow({
  result,
  active,
  onSelect,
}: {
  result: CommandResult;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        width: "100%",
        padding: "9px 16px",
        border: "none",
        background: active ? "rgba(29,78,216,0.06)" : "transparent",
        color: "#0F172A",
        fontFamily: "inherit",
        fontSize: 13,
        textAlign: "left",
        cursor: "pointer",
        transition: "background 80ms ease-out",
        outline: active ? "none" : undefined,
      }}
    >
      <span style={{ display: "inline-flex", color: "#94A3B8", flexShrink: 0, fontSize: 16 }}>
        {result.icon}
      </span>
      <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {result.label}
      </span>
      <span
        style={{
          fontSize: 11,
          color: "#94A3B8",
          background: "#F1F5F9",
          borderRadius: 4,
          padding: "2px 6px",
          flexShrink: 0,
          fontWeight: 500,
        }}
      >
        {TYPE_LABELS[result.type]}
      </span>
    </button>
  );
}

function buildResults(
  query: string,
  domains: Array<{ id: string; name: string; description?: string }>,
  guidelines: Array<{ code: string; title: string }>,
  prompts: Array<{ id: string; name: string }>,
): CommandResult[] {
  const q = query.toLowerCase();
  if (!q) return [];

  const results: CommandResult[] = [];

  domains
    .filter((d) => d.name.toLowerCase().includes(q) || d.description?.toLowerCase().includes(q))
    .slice(0, 3)
    .forEach((d) =>
      results.push({
        id: "domain-" + d.id,
        label: d.name,
        meta: d.description,
        type: "domain",
        tab: "domains",
        icon: <FolderOpenOutlinedIcon sx={{ fontSize: 16 }} />,
      })
    );

  guidelines
    .filter((g) => g.code.toLowerCase().includes(q) || g.title.toLowerCase().includes(q))
    .slice(0, 3)
    .forEach((g) =>
      results.push({
        id: "guideline-" + g.code,
        label: g.title,
        meta: g.code,
        type: "guideline",
        tab: "clinical-guidelines",
        icon: <MenuBookOutlinedIcon sx={{ fontSize: 16 }} />,
      })
    );

  prompts
    .filter((p) => p.name.toLowerCase().includes(q))
    .slice(0, 3)
    .forEach((p) =>
      results.push({
        id: "prompt-" + p.id,
        label: p.name,
        type: "prompt",
        tab: "ai-instructions",
        icon: <PsychologyOutlinedIcon sx={{ fontSize: 16 }} />,
      })
    );

  return results;
}

export function KnowledgeCommandPalette({
  open,
  onClose,
  onNavigate,
}: KnowledgeCommandPaletteProps) {
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const [domains, setDomains] = useState<Array<{ id: string; name: string; description?: string }>>([]);
  const [guidelines, setGuidelines] = useState<Array<{ code: string; title: string }>>([]);
  const [prompts, setPrompts] = useState<Array<{ id: string; name: string }>>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) { setQuery(""); setActiveIdx(0); return; }
    setTimeout(() => inputRef.current?.focus(), 60);
    fetchData();
  }, [open]);

  const fetchData = useCallback(async () => {
    try {
      const [domainsRes, promptsRes] = await Promise.allSettled([
        fetch("/api/proxy/analytics/domains").then((r) => r.json()),
        fetch("/api/prompts").then((r) => r.json()),
      ]);
      if (domainsRes.status === "fulfilled") {
        setDomains(Array.isArray(domainsRes.value) ? domainsRes.value : domainsRes.value.domains ?? []);
      }
      if (promptsRes.status === "fulfilled") {
        setPrompts(Array.isArray(promptsRes.value) ? promptsRes.value : []);
      }
    } catch {
      // non-fatal; empty results shown
    }
  }, []);

  const results = buildResults(query, domains, guidelines, prompts);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && results[activeIdx]) {
        onNavigate(results[activeIdx].tab);
        onClose();
      } else if (e.key === "Escape") {
        onClose();
      }
    },
    [results, activeIdx, onNavigate, onClose]
  );

  useEffect(() => { setActiveIdx(0); }, [results.length]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      aria-labelledby="knowledge-cmd-palette-title"
      sx={{ display: "flex", alignItems: "flex-start", justifyContent: "center", pt: "10vh" }}
    >
      <Box
        data-testid="knowledge-command-palette"
        sx={{
          width: "100%",
          maxWidth: 560,
          background: "#FFFFFF",
          borderRadius: 2,
          boxShadow: "0 24px 64px rgba(15,23,42,0.18)",
          overflow: "hidden",
          outline: "none",
        }}
        onKeyDown={handleKeyDown}
      >
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 2.5, py: 0 }}>
          <SearchIcon sx={{ color: "text.disabled", fontSize: 20, flexShrink: 0 }} />
          <InputBase
            inputRef={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search domains, guidelines, prompts..."
            fullWidth
            sx={{
              fontSize: 16,
              py: 2,
              "& input": { padding: 0 },
            }}
            id="knowledge-cmd-palette-title"
          />
          <span
            style={{
              fontSize: 10,
              color: "#CBD5E1",
              background: "#F1F5F9",
              border: "1px solid #E2E8F0",
              borderRadius: 4,
              padding: "2px 5px",
              fontFamily: "monospace",
              cursor: "pointer",
              flexShrink: 0,
            }}
            onClick={onClose}
            role="button"
            tabIndex={0}
          >
            Esc
          </span>
        </Box>

        {results.length > 0 ? (
          <>
            <Divider />
            <Box sx={{ maxHeight: 320, overflowY: "auto" }}>
              {results.map((r, i) => (
                <ResultRow
                  key={r.id}
                  result={r}
                  active={i === activeIdx}
                  onSelect={() => {
                    onNavigate(r.tab);
                    onClose();
                  }}
                />
              ))}
            </Box>
          </>
        ) : query.length > 0 ? (
          <>
            <Divider />
            <Box sx={{ p: 3, textAlign: "center", color: "text.secondary", fontSize: 13 }}>
              No results for &ldquo;{query}&rdquo;
            </Box>
          </>
        ) : null}

        <Divider />
        <Box
          sx={{
            display: "flex",
            justifyContent: "flex-end",
            gap: 1.5,
            px: 2,
            py: 1,
            color: "text.disabled",
            fontSize: 11,
          }}
        >
          <span><kbd style={{ fontFamily: "monospace" }}>{"\u2191\u2193"}</kbd> navigate</span>
          <span><kbd style={{ fontFamily: "monospace" }}>Enter</kbd> open</span>
          <span><kbd style={{ fontFamily: "monospace" }}>Esc</kbd> close</span>
        </Box>
      </Box>
    </Modal>
  );
}
