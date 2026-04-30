/**
 * ChartZoomDialog -- generic "expand chart" modal shell.
 *
 * Renders a MUI Dialog with a title bar and close button.  The content
 * area is intentionally minimal: children are responsible for their own
 * layout so each chart type can size itself correctly.
 *
 * Usage patterns:
 *   - Square SVG charts (radar, pyramid): wrap children in a Box with
 *     `sx={{ width: "100%", aspectRatio: "1" }}` so the responsive
 *     SVG auto-fills a proper square without any fixed pixel height.
 *   - Wide recharts (strip plots): wrap children in a Box with an
 *     explicit `sx={{ height: 360 }}` and pass a larger chartHeight prop
 *     to the chart component.
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
   * Max-width of the dialog.  Defaults to "sm" (600px) for square
   * charts.  Use "lg" for wide strip plots.
   */
  maxWidth?: "xs" | "sm" | "md" | "lg" | "xl";
}

export default function ChartZoomDialog({
  open,
  onClose,
  title,
  subtitle,
  children,
  maxWidth = "sm",
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

      <DialogContent sx={{ pt: "8px !important", pb: 3 }}>
        {children}
      </DialogContent>
    </Dialog>
  );
}
