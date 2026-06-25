"use client";

import type { ReactNode } from "react";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import RouteOutlinedIcon from "@mui/icons-material/RouteOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import GroupOutlinedIcon from "@mui/icons-material/GroupOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import SearchIcon from "@mui/icons-material/Search";
import type { KnowledgeTabKey } from "@/lib/knowledgeCopy";

interface TabDef {
  key: KnowledgeTabKey;
  label: string;
  icon: ReactNode;
}

interface SidebarGroup {
  label: string;
  tabs: TabDef[];
}

const SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    label: "NLP & AI",
    tabs: [
      { key: "training-data", label: "Training Data", icon: <SchoolOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "surface-forms", label: "Surface Forms", icon: <TextFieldsOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "context-rules", label: "Context Rules", icon: <AccountTreeOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "ai-instructions", label: "AI Instructions", icon: <PsychologyOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "ai-summarisation", label: "AI Summarisation", icon: <AutoAwesomeOutlinedIcon sx={{ fontSize: 18 }} /> },
    ],
  },
  {
    label: "Clinical Knowledge",
    tabs: [
      { key: "domains", label: "Domains", icon: <FolderOpenOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "clinical-guidelines", label: "Clinical Guidelines", icon: <MenuBookOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "pathways", label: "Pathways", icon: <RouteOutlinedIcon sx={{ fontSize: 18 }} /> },
    ],
  },
  {
    label: "Data Setup",
    tabs: [
      { key: "terminology", label: "Terminology", icon: <HubOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "results-labs", label: "Results / Labs", icon: <ScienceOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "extraction-scenarios", label: "Extraction Scenarios", icon: <BiotechOutlinedIcon sx={{ fontSize: 18 }} /> },
    ],
  },
  {
    label: "Quality",
    tabs: [
      { key: "test-patients", label: "Test Patients", icon: <GroupOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "coding-validation", label: "Coding Validation", icon: <FactCheckOutlinedIcon sx={{ fontSize: 18 }} /> },
    ],
  },
];

interface KnowledgeSidebarProps {
  activeKey: KnowledgeTabKey;
  onTabChange: (key: KnowledgeTabKey) => void;
  onSearchClick?: () => void;
}

const BRAND = "#1D4ED8";
const BRAND_BG = "rgba(29,78,216,0.08)";

function GroupHeading({ label }: { label: string }) {
  return (
    <div
      style={{
        padding: "8px 12px 4px",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "#94A3B8",
        userSelect: "none",
      }}
    >
      {label}
    </div>
  );
}

function NavItem({
  tab,
  active,
  onClick,
}: {
  tab: TabDef;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={tab.label}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        width: "100%",
        padding: "7px 10px 7px 12px",
        margin: "1px 0",
        border: "none",
        borderRadius: 8,
        background: active ? BRAND_BG : "transparent",
        color: active ? BRAND : "#475569",
        fontFamily: "inherit",
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        textAlign: "left",
        cursor: "pointer",
        transition: "background 120ms ease-out, color 120ms ease-out",
        position: "relative",
        outline: "none",
      }}
      aria-current={active ? "page" : undefined}
    >
      {active && (
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            left: 0,
            top: 6,
            bottom: 6,
            width: 3,
            borderRadius: 999,
            background: BRAND,
          }}
        />
      )}
      <span style={{ display: "inline-flex", flexShrink: 0 }}>{tab.icon}</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {tab.label}
      </span>
    </button>
  );
}

export function KnowledgeSidebar({
  activeKey,
  onTabChange,
  onSearchClick,
}: KnowledgeSidebarProps) {
  return (
    <nav
      data-testid="knowledge-sidebar"
      aria-label="Knowledge sections"
      style={{
        width: 240,
        flexShrink: 0,
        position: "sticky",
        top: 0,
        height: "100vh",
        overflowY: "auto",
        borderRight: "1px solid #E2E8F0",
        background: "#FFFFFF",
        display: "flex",
        flexDirection: "column",
        padding: "12px 8px 24px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          fontSize: 15,
          fontWeight: 700,
          color: "#0F172A",
          padding: "4px 12px 12px",
          letterSpacing: -0.2,
        }}
      >
        Knowledge
      </div>

      <button
        type="button"
        onClick={onSearchClick}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          width: "100%",
          padding: "7px 10px",
          marginBottom: 8,
          border: "1px solid #E2E8F0",
          borderRadius: 8,
          background: "#F8FAFC",
          color: "#94A3B8",
          fontFamily: "inherit",
          fontSize: 12,
          cursor: "pointer",
          textAlign: "left",
          outline: "none",
        }}
        aria-label="Search knowledge (Cmd+K)"
      >
        <SearchIcon sx={{ fontSize: 14 }} />
        <span style={{ flex: 1 }}>Search...</span>
        <span
          style={{
            fontSize: 10,
            color: "#CBD5E1",
            background: "#F1F5F9",
            border: "1px solid #E2E8F0",
            borderRadius: 4,
            padding: "1px 5px",
            fontFamily: "monospace",
          }}
        >
          {"\u2318"}K
        </span>
      </button>

      {SIDEBAR_GROUPS.map((group) => (
        <div key={group.label} style={{ marginBottom: 4 }}>
          <GroupHeading label={group.label} />
          {group.tabs.map((tab) => (
            <NavItem
              key={tab.key}
              tab={tab}
              active={tab.key === activeKey}
              onClick={() => onTabChange(tab.key)}
            />
          ))}
        </div>
      ))}

      <div style={{ marginTop: "auto", padding: "8px 12px 0" }}>
        <span
          style={{
            fontSize: 11,
            color: "#CBD5E1",
            display: "block",
            textAlign: "center",
          }}
        >
          Press {"\u2318"}K to search
        </span>
      </div>
    </nav>
  );
}

export { SIDEBAR_GROUPS };
export type { TabDef, SidebarGroup };
