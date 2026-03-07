"use client";

import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ReviewSection from "@/components/operations/ReviewSection";

export default function OperationsReviewsPage() {
  const [msg, setMsg] = useState<string>("");
  const [busy, setBusy] = useState(false);

  async function clearResolved() {
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch("/api/training/coding-review/resolved", { method: "DELETE" });
      if (!res.ok) throw new Error(`${res.status}`);
      const body = await res.json();
      setMsg(`Cleared ${body.deleted ?? 0} resolved review items.`);
    } catch {
      setMsg("Could not clear resolved review items.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1000, mx: "auto" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h5" sx={{ fontWeight: 700 }}>
          Things to check
        </Typography>
        <Button variant="outlined" size="small" onClick={clearResolved} disabled={busy}>
          Clear resolved
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Review coding, context, HITL and surface-form tasks.
      </Typography>
      {msg && <Alert sx={{ mb: 2 }} severity={msg.startsWith("Cleared") ? "success" : "error"}>{msg}</Alert>}
      <ReviewSection />
    </Box>
  );
}

