/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-2E8544FD
 *   DI: DI-C65FD45B
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-2E8544FD")
 */
"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";

export interface TocSection {
  id: string;
  label: string;
  group?: string;
}

interface AuditReportShellProps {
  sections: TocSection[];
  pendingScrollSectionId?: string | null;
  pendingScrollReady?: boolean;
  onPendingScrollHandled?: () => void;
  children: React.ReactNode;
}

const TOC_WIDTH = 220;
const SCROLL_LOCK_MS = 5_000;

export default function AuditReportShell({
  sections,
  pendingScrollSectionId = null,
  pendingScrollReady = true,
  onPendingScrollHandled,
  children,
}: AuditReportShellProps) {
  const theme = useTheme();
  const isMdUp = useMediaQuery(theme.breakpoints.up("lg"));
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? "");
  const observerRef = useRef<IntersectionObserver | null>(null);
  const scrollLockRef = useRef<{ id: string; expiresAt: number } | null>(null);
  const scrollFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!isMdUp) return;
    const sectionEls = sections
      .map(({ id }) => document.getElementById(id))
      .filter(Boolean) as HTMLElement[];

    observerRef.current?.disconnect();
    observerRef.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id);
            break;
          }
        }
      },
      { rootMargin: "-10% 0px -70% 0px", threshold: 0 },
    );
    sectionEls.forEach((el) => observerRef.current!.observe(el));
    return () => observerRef.current?.disconnect();
  }, [sections, isMdUp]);

  const scrollToSection = (id: string, behavior: ScrollBehavior) => {
    const el = document.getElementById(id);
    if (!el) return false;
    el.scrollIntoView({ behavior, block: "start" });
    setActiveId(id);
    return true;
  };

  const lockToSection = (id: string, behavior: ScrollBehavior = "smooth") => {
    scrollLockRef.current = { id, expiresAt: Date.now() + SCROLL_LOCK_MS };
    scrollToSection(id, behavior);
  };

  useEffect(() => {
    if (!pendingScrollSectionId || !pendingScrollReady) return;
    lockToSection(pendingScrollSectionId);
    onPendingScrollHandled?.();
    // onPendingScrollHandled is intentionally omitted; callers often pass an
    // inline setter and we only want this to fire when the target/readiness changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingScrollSectionId, pendingScrollReady]);

  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      const lock = scrollLockRef.current;
      if (!lock) return;
      if (Date.now() > lock.expiresAt) {
        scrollLockRef.current = null;
        return;
      }
      if (scrollFrameRef.current != null) cancelAnimationFrame(scrollFrameRef.current);
      scrollFrameRef.current = requestAnimationFrame(() => {
        scrollToSection(lock.id, "auto");
      });
    });

    observer.observe(document.body);
    return () => {
      observer.disconnect();
      if (scrollFrameRef.current != null) cancelAnimationFrame(scrollFrameRef.current);
    };
  }, []);

  const handleTocClick = (id: string) => {
    if (scrollToSection(id, "smooth")) {
      scrollLockRef.current = { id, expiresAt: Date.now() + SCROLL_LOCK_MS };
    }
  };

  const toc = (
    <Box
      component="nav"
      aria-label="Report sections"
      sx={{
        width: TOC_WIDTH,
        flexShrink: 0,
        position: "sticky",
        top: 24,
        maxHeight: "calc(100vh - 40px)",
        overflowY: "auto",
        display: { xs: "none", lg: "block" },
        borderRight: "1px solid",
        borderColor: "divider",
        pr: 1,
      }}
    >
      <Typography
        variant="overline"
        sx={{ px: 2, pt: 1.5, pb: 0.5, display: "block", fontSize: "0.68rem", color: "text.secondary", letterSpacing: 1 }}
      >
        Sections
      </Typography>
      <List dense disablePadding>
        {sections.map((sec, idx) => {
          const prevGroup = idx > 0 ? sections[idx - 1].group : undefined;
          const showDivider = sec.group && sec.group !== prevGroup && idx > 0;
          return (
            <Box key={sec.id}>
              {showDivider && <Divider sx={{ my: 0.5 }} />}
              <ListItemButton
                selected={activeId === sec.id}
                onClick={() => handleTocClick(sec.id)}
                sx={{
                  borderRadius: 1,
                  py: 0.5,
                  px: 2,
                  "&.Mui-selected": {
                    bgcolor: "primary.50",
                    borderLeft: "3px solid",
                    borderColor: "primary.main",
                    pl: "13px",
                  },
                }}
              >
                <ListItemText
                  primary={sec.label}
                  primaryTypographyProps={{
                    fontSize: "0.78rem",
                    fontWeight: activeId === sec.id ? 700 : 400,
                    color: activeId === sec.id ? "primary.main" : "text.primary",
                  }}
                />
              </ListItemButton>
            </Box>
          );
        })}
      </List>
    </Box>
  );

  return (
    <Box sx={{ display: "flex", gap: 2, alignItems: "flex-start" }}>
      {toc}
      <Box sx={{ flex: 1, minWidth: 0 }}>{children}</Box>
    </Box>
  );
}
