/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-30A82196
 *   DI: DI-85B110A5
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-30A82196")
 */
"use client";

import type { ReactNode } from "react";
import { motion as fm } from "framer-motion";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import TextFieldsOutlinedIcon from "@mui/icons-material/TextFieldsOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import RouteOutlinedIcon from "@mui/icons-material/RouteOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import ScienceIcon from "@mui/icons-material/Science";
import SearchIcon from "@mui/icons-material/Search";
import {
  frostStyle,
  springOrInstant,
  springs,
  tapScale,
  useMotion,
  useReducedTransparency,
} from "@leo/design-system";
import { color, elevation, radius, typography } from "@leo/design-system/tokens";
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
      { key: "surface-forms", label: "Phrase mappings", icon: <TextFieldsOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "context-rules", label: "Context Rules", icon: <AccountTreeOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "guard-rules", label: "Pipeline Guards", icon: <ShieldOutlinedIcon sx={{ fontSize: 18 }} /> },
      { key: "ai-instructions", label: "AI Instructions", icon: <PsychologyOutlinedIcon sx={{ fontSize: 18 }} /> },
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
    ],
  },
  {
    label: "Quality",
    tabs: [
      { key: "validation-lab", label: "Validation Lab", icon: <ScienceIcon sx={{ fontSize: 18 }} /> },
    ],
  },
];

interface KnowledgeSidebarProps {
  activeKey: KnowledgeTabKey;
  onTabChange: (key: KnowledgeTabKey) => void;
  onSearchClick?: () => void;
}

const BRAND = color.brand.primary;
const WELL = "rgba(15, 23, 42, 0.06)";

function GroupHeading({ label }: { label: string }) {
  return (
    <div
      style={{
        padding: "14px 12px 6px",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: typography.letterSpacing.caption,
        textTransform: "uppercase",
        color: color.text.caption,
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
  reducedMotion,
}: {
  tab: TabDef;
  active: boolean;
  onClick: () => void;
  reducedMotion: boolean;
}) {
  return (
    <fm.button
      type="button"
      onClick={onClick}
      title={tab.label}
      whileTap={tapScale(reducedMotion)}
      whileHover={
        reducedMotion || active ? undefined : { backgroundColor: WELL }
      }
      transition={springOrInstant(reducedMotion, springs.press)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        width: "100%",
        padding: "8px 10px 8px 12px",
        margin: "2px 0",
        border: "none",
        borderRadius: radius.sm,
        background: active ? color.surface.raised : "transparent",
        boxShadow: active ? elevation.card : "none",
        color: active ? BRAND : color.text.secondary,
        fontFamily: typography.fontFamily.body,
        fontSize: 13,
        fontWeight: active ? 600 : 400,
        textAlign: "left",
        cursor: "pointer",
        position: "relative",
        outline: "none",
      }}
      aria-current={active ? "page" : undefined}
    >
      {active ? (
        <fm.span
          layoutId={reducedMotion ? undefined : "knowledge-nav-rail"}
          aria-hidden="true"
          transition={springOrInstant(reducedMotion, springs.ui)}
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
      ) : null}
      <span style={{ display: "inline-flex", flexShrink: 0 }}>{tab.icon}</span>
      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {tab.label}
      </span>
    </fm.button>
  );
}

export function KnowledgeSidebar({
  activeKey,
  onTabChange,
  onSearchClick,
}: KnowledgeSidebarProps) {
  const { reducedMotion } = useMotion();
  const frost = frostStyle(useReducedTransparency(), "pane");

  return (
    <nav
      data-testid="knowledge-sidebar"
      aria-label="Knowledge sections"
      style={{
        width: 248,
        flexShrink: 0,
        position: "sticky",
        top: 0,
        height: "100vh",
        overflowY: "auto",
        borderRight: "1px solid " + color.surface.divider,
        borderTop: "1px solid rgba(255, 255, 255, 0.7)",
        boxShadow: "4px 0 24px rgba(15, 23, 42, 0.08)",
        ...frost,
        display: "flex",
        flexDirection: "column",
        padding: "16px 10px 24px",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          fontFamily: typography.fontFamily.heading,
          fontSize: 18,
          fontWeight: 700,
          lineHeight: 1.15,
          color: color.text.primary,
          padding: "4px 12px 14px",
          letterSpacing: typography.letterSpacing.display,
        }}
      >
        Knowledge
      </div>

      <fm.button
        type="button"
        onClick={onSearchClick}
        whileTap={tapScale(reducedMotion)}
        transition={springOrInstant(reducedMotion, springs.press)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          width: "100%",
          padding: "8px 12px",
          marginBottom: 4,
          border: "none",
          borderRadius: radius.pill,
          background: WELL,
          boxShadow: "inset 0 1px 2px rgba(15, 23, 42, 0.08)",
          color: color.text.secondary,
          fontFamily: typography.fontFamily.body,
          fontSize: 13,
          cursor: "pointer",
          textAlign: "left",
          outline: "none",
        }}
        aria-label="Search knowledge (Cmd+K)"
      >
        <SearchIcon sx={{ fontSize: 14 }} />
        <span style={{ flex: 1 }}>Search...</span>
        <span
          aria-hidden="true"
          style={{
            fontSize: 10,
            color: color.text.caption,
            background: color.surface.raised,
            border: "1px solid " + color.surface.divider,
            borderRadius: radius.xs,
            padding: "1px 5px",
            fontFamily: typography.fontFamily.mono,
          }}
        >
          {"\u2318"}K
        </span>
      </fm.button>

      {SIDEBAR_GROUPS.map((group) => (
        <div key={group.label} style={{ marginBottom: 4 }}>
          <GroupHeading label={group.label} />
          {group.tabs.map((tab) => (
            <NavItem
              key={tab.key}
              tab={tab}
              active={tab.key === activeKey}
              onClick={() => onTabChange(tab.key)}
              reducedMotion={reducedMotion}
            />
          ))}
        </div>
      ))}

      <div style={{ marginTop: "auto", padding: "8px 12px 0" }}>
        <span
          style={{
            fontSize: 11,
            color: color.text.secondary,
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
