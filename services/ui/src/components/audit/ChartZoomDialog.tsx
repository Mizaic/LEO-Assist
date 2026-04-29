/**
 * ChartZoomDialog -- generic "expand chart" modal shell.
 *
 * Any chart card that has a small on-page footprint can pass an
 * `onZoom` callback to trigger this dialog.  Because all chart
 * primitives (SVG radar cards, Recharts ResponsiveContainer strip
 * plots, population pyramids) are responsive, they auto-size to
 * fill the larger dialog container without any extra prop changes.
 */
"use client";

import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import Box from "@mui/material/Box";
import CloseIcon from "@mui/icons-material/Close";

interface ChartZoomDialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  /**
   * Max-width of the dialog.  Defaults to "md" (960px).
   * Use "sm" for square radar charts, "lg" for wide strip plots.
   */
  maxWidth?: "xs" | "sm" | "md" | "lg" | "xl";
  /** Override the inner content box height (px).  Defaults to 520. */
  contentHeight?: number;
}

export default function ChartZoomDialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  maxWidth = "md",
  contentHeight = 520,
}: ChartZoomDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth
      aria-labelledby="chart-zoom-dialog-title"
    >
      <DialogTitle
        id="chart-zoom-dialog-title"
        sx={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 1,
          pb: subtitle ? 0.5 : 1,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Typography
            component="span"
            sx={{ fontSize: "1rem", fontWeight: 700, display: "block" }}
          >
            {title}
          </Typography>
          {subtitle && (
            <Typography
              component="span"
              sx={{
                fontSize: "0.78rem",
                color: "text.secondary",
                display: "block",
                mt: 0.25,
              }}
            >
              {subtitle}
            </Typography>
          )}
        </Box>
        <IconButton
          aria-label="Close expanded chart"
          onClick={onClose}
          size="small"
          sx={{ flexShrink: 0, mt: -0.25 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ pt: "8px !important", pb: 2 }}>
        <Box
          sx={{
            height: contentHeight,
            width: "100%",
            display: "flex",
            alignItems: "stretch",
          }}
        >
          {children}
        </Box>
      </DialogContent>
    </Dialog>
  );
}
