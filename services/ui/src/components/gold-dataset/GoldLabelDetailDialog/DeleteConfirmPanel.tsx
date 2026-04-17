/**
 * DeleteConfirmPanel -- Wave E Phase 2a-iv
 *
 * The slide-in confirmation strip shown above the footer when the
 * reviewer chooses Delete from the actions kebab. Lifted verbatim
 * from the inline JSX in the legacy GoldLabelDetailDialog so
 * behaviour is preserved (suppress-on-delete checkbox, two-button
 * confirm/cancel pattern), but restyled to use design-system
 * surface tones and motion.
 */
"use client";

import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { motion } from "framer-motion";

interface DeleteConfirmPanelProps {
  suppressOnDelete: boolean;
  onSuppressChange: (suppress: boolean) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export default function DeleteConfirmPanel(props: DeleteConfirmPanelProps) {
  const { suppressOnDelete, onSuppressChange, onCancel, onConfirm } = props;
  return (
    <motion.div
      data-testid="delete-confirm-panel"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 6 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
    >
      <Box
        sx={{
          px: 2.25,
          py: 1.5,
          borderTop: "1px solid",
          borderColor: "error.light",
          bgcolor: "#FEF2F2",
          display: "flex",
          flexDirection: "column",
          gap: 0.75,
        }}
      >
        <Typography
          variant="body2"
          sx={{ fontWeight: 600, color: "error.dark" }}
        >
          Delete this sentence?
        </Typography>
        <Typography variant="caption" color="text.secondary">
          This removes the candidate and any linked gold labels. It
          cannot be undone.
        </Typography>
        <FormControlLabel
          control={
            <Checkbox
              size="small"
              checked={suppressOnDelete}
              onChange={(event) => onSuppressChange(event.target.checked)}
              color="error"
            />
          }
          label={
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              Also block this sentence from future pipeline runs
            </Typography>
          }
        />
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            variant="outlined"
            onClick={onCancel}
            data-testid="delete-cancel-button"
            sx={{ textTransform: "none" }}
          >
            Cancel
          </Button>
          <Button
            size="small"
            variant="contained"
            color="error"
            onClick={onConfirm}
            data-testid="delete-confirm-button"
            sx={{ textTransform: "none" }}
          >
            {suppressOnDelete ? "Delete and block" : "Delete"}
          </Button>
        </Stack>
      </Box>
    </motion.div>
  );
}
