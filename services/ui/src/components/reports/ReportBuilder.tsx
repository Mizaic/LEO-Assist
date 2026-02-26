"use client";

import { useState, useCallback } from "react";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ElementPalette from "./ElementPalette";
import ElementRenderer from "./ElementRenderer";

export interface ReportElement {
  id: string;
  type: "heading" | "text" | "kpi_card" | "chart" | "measure_result" | "divider" | "table";
  props: Record<string, any>;
}

export default function ReportBuilder() {
  const [elements, setElements] = useState<ReportElement[]>([
    { id: "el-1", type: "heading", props: { text: "Clinical Audit Report", level: 1 } },
    { id: "el-2", type: "text", props: { text: "This report summarises the clinical audit findings." } },
  ]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showPalette, setShowPalette] = useState(false);

  const addElement = useCallback(
    (type: ReportElement["type"]) => {
      const id = `el-${Date.now()}`;
      const defaults: Record<string, Record<string, any>> = {
        heading: { text: "New Section", level: 2 },
        text: { text: "Enter text here..." },
        kpi_card: { title: "KPI", value: "—", unit: "days" },
        chart: { title: "Chart", chartType: "bar", measureId: "" },
        measure_result: { measureId: "", title: "Measure Result" },
        divider: {},
        table: { title: "Data Table", columns: [], rows: [] },
      };
      setElements((prev) => [...prev, { id, type, props: defaults[type] ?? {} }]);
      setShowPalette(false);
      setSelectedId(id);
    },
    [],
  );

  const removeElement = useCallback((id: string) => {
    setElements((prev) => prev.filter((e) => e.id !== id));
    setSelectedId(null);
  }, []);

  const moveElement = useCallback((id: string, direction: -1 | 1) => {
    setElements((prev) => {
      const idx = prev.findIndex((e) => e.id === id);
      if (idx < 0) return prev;
      const newIdx = idx + direction;
      if (newIdx < 0 || newIdx >= prev.length) return prev;
      const copy = [...prev];
      [copy[idx], copy[newIdx]] = [copy[newIdx], copy[idx]];
      return copy;
    });
  }, []);

  const updateProps = useCallback((id: string, newProps: Record<string, any>) => {
    setElements((prev) =>
      prev.map((e) => (e.id === id ? { ...e, props: { ...e.props, ...newProps } } : e)),
    );
  }, []);

  return (
    <Box sx={{ display: "flex", height: "calc(100vh - 64px)" }}>
      {/* Canvas */}
      <Box sx={{ flex: 1, p: 3, overflow: "auto" }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
          <Typography variant="h5">Report Builder</Typography>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={() => setShowPalette((p) => !p)}
            >
              Add Element
            </Button>
            <Button variant="contained" startIcon={<SaveOutlinedIcon />}>
              Save
            </Button>
          </Box>
        </Box>

        {showPalette && (
          <Box sx={{ mb: 2 }}>
            <ElementPalette onAdd={addElement} />
          </Box>
        )}

        <Paper
          variant="outlined"
          sx={{ minHeight: 600, p: 3, bgcolor: "white" }}
        >
          {elements.map((el, idx) => (
            <Box
              key={el.id}
              onClick={() => setSelectedId(el.id)}
              sx={{
                position: "relative",
                border: "2px solid",
                borderColor: selectedId === el.id ? "primary.main" : "transparent",
                borderRadius: 1,
                p: 1.5,
                mb: 1,
                cursor: "pointer",
                "&:hover": {
                  borderColor: selectedId === el.id ? "primary.main" : "grey.300",
                },
              }}
            >
              {selectedId === el.id && (
                <Box
                  sx={{
                    position: "absolute",
                    top: -16,
                    right: 0,
                    display: "flex",
                    gap: 0.25,
                    bgcolor: "background.paper",
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    px: 0.5,
                  }}
                >
                  <Tooltip title="Move up">
                    <IconButton size="small" onClick={() => moveElement(el.id, -1)} disabled={idx === 0}>
                      <ArrowUpwardIcon sx={{ fontSize: 16 }} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Move down">
                    <IconButton
                      size="small"
                      onClick={() => moveElement(el.id, 1)}
                      disabled={idx === elements.length - 1}
                    >
                      <ArrowDownwardIcon sx={{ fontSize: 16 }} />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton size="small" onClick={() => removeElement(el.id)}>
                      <DeleteOutlineIcon sx={{ fontSize: 16, color: "error.main" }} />
                    </IconButton>
                  </Tooltip>
                </Box>
              )}
              <ElementRenderer
                element={el}
                isSelected={selectedId === el.id}
                onUpdateProps={(props) => updateProps(el.id, props)}
              />
            </Box>
          ))}

          {elements.length === 0 && (
            <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
              <Typography>Click &quot;Add Element&quot; to start building your report</Typography>
            </Box>
          )}
        </Paper>
      </Box>
    </Box>
  );
}
