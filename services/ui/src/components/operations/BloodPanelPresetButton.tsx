/**
 * "Add standard blood panel" action for an ordered_tests section.
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */
"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";

import { fetchBloodPanelPreset, PRESET_LOAD_ERROR } from "./bloodPanelPresets";
import type { FormSchemaItem } from "./formSchemaDetector";

export function BloodPanelPresetButton({
  onAdd,
}: {
  onAdd: (items: FormSchemaItem[]) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  async function handleClick() {
    setLoading(true);
    setMessage("");
    setFailed(false);
    try {
      const items = await fetchBloodPanelPreset();
      onAdd(items);
      setMessage(
        `Added ${items.length} standard blood tests. Delete any row this form does not use.`,
      );
    } catch {
      setFailed(true);
      setMessage(PRESET_LOAD_ERROR);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Box sx={{ mb: 1 }}>
      <Button
        size="small"
        variant="outlined"
        startIcon={
          loading ? (
            <CircularProgress size={14} color="inherit" aria-label="Loading" />
          ) : (
            <ScienceOutlinedIcon fontSize="small" />
          )
        }
        onClick={() => void handleClick()}
        disabled={loading}
      >
        {loading ? "Loading blood panel..." : "Add standard blood panel"}
      </Button>
      <Typography
        variant="caption"
        aria-live="polite"
        color={failed ? "error" : "text.secondary"}
        sx={{ display: "block", mt: 0.5 }}
      >
        {message ||
          "Loads the usual NHS blood tests with their SNOMED codes already filled in."}
      </Typography>
    </Box>
  );
}
