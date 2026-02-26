"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import Typography from "@mui/material/Typography";
import TitleIcon from "@mui/icons-material/Title";
import TextFieldsIcon from "@mui/icons-material/TextFields";
import BarChartIcon from "@mui/icons-material/BarChart";
import DashboardIcon from "@mui/icons-material/Dashboard";
import AssessmentIcon from "@mui/icons-material/Assessment";
import HorizontalRuleIcon from "@mui/icons-material/HorizontalRule";
import TableChartIcon from "@mui/icons-material/TableChart";

const ELEMENT_TYPES = [
  { type: "heading" as const, label: "Heading", icon: <TitleIcon />, desc: "Section heading" },
  { type: "text" as const, label: "Text", icon: <TextFieldsIcon />, desc: "Free text paragraph" },
  { type: "kpi_card" as const, label: "KPI Card", icon: <DashboardIcon />, desc: "Key metric card" },
  { type: "chart" as const, label: "Chart", icon: <BarChartIcon />, desc: "Bar/line chart" },
  { type: "measure_result" as const, label: "Measure Result", icon: <AssessmentIcon />, desc: "FHIR Measure evaluation" },
  { type: "table" as const, label: "Table", icon: <TableChartIcon />, desc: "Data table" },
  { type: "divider" as const, label: "Divider", icon: <HorizontalRuleIcon />, desc: "Visual separator" },
];

export default function ElementPalette({
  onAdd,
}: {
  onAdd: (type: "heading" | "text" | "kpi_card" | "chart" | "measure_result" | "divider" | "table") => void;
}) {
  return (
    <Card variant="outlined" sx={{ p: 2 }}>
      <Typography variant="body2" sx={{ fontWeight: 600, mb: 1.5, fontSize: "0.85rem" }}>
        Add an element
      </Typography>
      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
        {ELEMENT_TYPES.map((et) => (
          <Button
            key={et.type}
            variant="outlined"
            size="small"
            startIcon={et.icon}
            onClick={() => onAdd(et.type)}
            sx={{
              textTransform: "none",
              flexDirection: "column",
              gap: 0.25,
              py: 1,
              px: 2,
              minWidth: 100,
              "& .MuiButton-startIcon": { margin: 0 },
            }}
          >
            <Typography sx={{ fontSize: "0.75rem", fontWeight: 600 }}>{et.label}</Typography>
            <Typography sx={{ fontSize: "0.65rem", color: "text.secondary" }}>{et.desc}</Typography>
          </Button>
        ))}
      </Box>
    </Card>
  );
}
