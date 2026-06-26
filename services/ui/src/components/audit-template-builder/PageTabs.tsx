"use client";

/**
 * Page (tab) strip for the template builder. Lets a Quality Manager split a
 * report into multiple named pages, rename them, and remove them.
 *
 * Atlas trace:
 *   DO: DO-A9863AB6
 *   DI: DI-AUDIT-PAGES
 */

import { useState } from "react";
import Box from "@mui/material/Box";
import Tabs from "@mui/material/Tabs";
import Tab from "@mui/material/Tab";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import AddIcon from "@mui/icons-material/Add";
import MoreVertIcon from "@mui/icons-material/MoreVert";

import type { AuditPage } from "@/lib/auditTemplateApi";

interface PageTabsProps {
  pages: AuditPage[];
  activePageId: string;
  onSelect: (pageId: string) => void;
  onAdd: () => void;
  onRename: (pageId: string, title: string) => void;
  onDelete: (pageId: string) => void;
}

export default function PageTabs({
  pages,
  activePageId,
  onSelect,
  onAdd,
  onRename,
  onDelete,
}: PageTabsProps) {
  const [menu, setMenu] = useState<{ anchor: HTMLElement; pageId: string } | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const startRename = (page: AuditPage) => {
    setEditingId(page.page_id);
    setDraft(page.title);
    setMenu(null);
  };

  const commitRename = () => {
    if (editingId && draft.trim()) onRename(editingId, draft.trim());
    setEditingId(null);
  };

  return (
    <Box sx={{ display: "flex", alignItems: "center", borderBottom: "1px solid", borderColor: "divider" }}>
      <Tabs
        value={activePageId}
        onChange={(_, v) => onSelect(v)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ minHeight: 40, flex: 1 }}
      >
        {pages.map((page) => (
          <Tab
            key={page.page_id}
            value={page.page_id}
            sx={{ minHeight: 40, textTransform: "none", py: 0 }}
            label={
              editingId === page.page_id ? (
                <TextField
                  autoFocus
                  variant="standard"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  inputProps={{ "aria-label": "Page title", style: { fontSize: 13, width: 110 } }}
                />
              ) : (
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <span>{page.title}</span>
                  <Box
                    component="span"
                    role="button"
                    aria-label={`Page options for ${page.title}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenu({ anchor: e.currentTarget as HTMLElement, pageId: page.page_id });
                    }}
                    sx={{ display: "inline-flex", opacity: 0.6, "&:hover": { opacity: 1 } }}
                  >
                    <MoreVertIcon sx={{ fontSize: 15 }} />
                  </Box>
                </Box>
              )
            }
          />
        ))}
      </Tabs>

      <Tooltip title="Add page">
        <IconButton size="small" onClick={onAdd} aria-label="Add page" sx={{ mx: 0.5 }}>
          <AddIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      <Menu anchorEl={menu?.anchor} open={Boolean(menu)} onClose={() => setMenu(null)}>
        <MenuItem
          onClick={() => {
            const page = pages.find((p) => p.page_id === menu?.pageId);
            if (page) startRename(page);
          }}
        >
          Rename
        </MenuItem>
        <MenuItem
          disabled={pages.length <= 1}
          onClick={() => {
            if (menu) onDelete(menu.pageId);
            setMenu(null);
          }}
        >
          Delete page
        </MenuItem>
      </Menu>
    </Box>
  );
}
