"use client";

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import TextField from "@mui/material/TextField";
import type { ReportElement } from "./ReportBuilder";

interface Props {
  element: ReportElement;
  isSelected: boolean;
  onUpdateProps: (props: Record<string, any>) => void;
}

export default function ElementRenderer({ element, isSelected, onUpdateProps }: Props) {
  switch (element.type) {
    case "heading":
      return isSelected ? (
        <TextField
          value={element.props.text ?? ""}
          onChange={(e) => onUpdateProps({ text: e.target.value })}
          variant="standard"
          fullWidth
          slotProps={{
            input: {
              sx: {
                fontSize: element.props.level === 1 ? "1.8rem" : "1.3rem",
                fontWeight: 700,
              },
            },
          }}
        />
      ) : (
        <Typography
          variant={element.props.level === 1 ? "h4" : "h5"}
          sx={{ fontWeight: 700 }}
        >
          {element.props.text || "Heading"}
        </Typography>
      );

    case "text":
      return isSelected ? (
        <TextField
          value={element.props.text ?? ""}
          onChange={(e) => onUpdateProps({ text: e.target.value })}
          variant="standard"
          fullWidth
          multiline
          minRows={2}
        />
      ) : (
        <Typography variant="body1">{element.props.text || "Text content"}</Typography>
      );

    case "kpi_card":
      return (
        <Box
          sx={{
            display: "inline-flex",
            flexDirection: "column",
            px: 3,
            py: 2,
            borderRadius: 2,
            bgcolor: "primary.50",
            border: "1px solid",
            borderColor: "primary.100",
            minWidth: 160,
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, mb: 0.5 }}>
            {element.props.title ?? "KPI"}
          </Typography>
          <Typography variant="h4" sx={{ color: "primary.main" }}>
            {element.props.value ?? "—"}
            {element.props.unit && (
              <Typography component="span" variant="body2" sx={{ ml: 0.5 }}>
                {element.props.unit}
              </Typography>
            )}
          </Typography>
        </Box>
      );

    case "chart":
      return (
        <Box
          sx={{
            height: 200,
            borderRadius: 2,
            bgcolor: "grey.50",
            border: "1px dashed",
            borderColor: "grey.300",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography color="text.secondary">
            Chart: {element.props.title || "Configure measure"}
          </Typography>
        </Box>
      );

    case "measure_result":
      return (
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            bgcolor: "info.50",
            border: "1px solid",
            borderColor: "info.100",
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            {element.props.title ?? "Measure Result"}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {element.props.measureId
              ? `Evaluates Measure/${element.props.measureId}`
              : "Select a measure to evaluate"}
          </Typography>
        </Box>
      );

    case "divider":
      return <Divider sx={{ my: 1 }} />;

    case "table":
      return (
        <Box
          sx={{
            p: 2,
            borderRadius: 2,
            border: "1px dashed",
            borderColor: "grey.300",
            bgcolor: "grey.50",
          }}
        >
          <Typography color="text.secondary" sx={{ fontSize: "0.85rem" }}>
            Table: {element.props.title || "Configure data source"}
          </Typography>
        </Box>
      );

    default:
      return <Typography color="error">Unknown element type</Typography>;
  }
}
