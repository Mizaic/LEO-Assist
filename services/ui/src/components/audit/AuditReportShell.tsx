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
  children: React.ReactNode;
}

const TOC_WIDTH = 220;

export default function AuditReportShell({ sections, children }: AuditReportShellProps) {
  const theme = useTheme();
  const isMdUp = useMediaQuery(theme.breakpoints.up("lg"));
  const [activeId, setActiveId] = useState<string>(sections[0]?.id ?? "");
  const observerRef = useRef<IntersectionObserver | null>(null);

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

  const handleTocClick = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveId(id);
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
        top: 72,
        maxHeight: "calc(100vh - 88px)",
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
