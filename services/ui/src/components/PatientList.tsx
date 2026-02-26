"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import InputAdornment from "@mui/material/InputAdornment";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardActionArea from "@mui/material/CardActionArea";
import LinearProgress from "@mui/material/LinearProgress";
import Skeleton from "@mui/material/Skeleton";
import SearchIcon from "@mui/icons-material/Search";
import RefreshIcon from "@mui/icons-material/Refresh";
import { Virtuoso } from "react-virtuoso";
import { fetchPatients } from "@/lib/api";
import type { Patient } from "@/lib/types";

export default function PatientList() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    try {
      setPatients(await fetchPatients());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Could not load patients. Check your connection and try Refresh.");
    } finally {
      setLoading(false);
    }
  }

  const normalizedQuery = query.trim().toLowerCase();
  const filteredPatients = normalizedQuery
    ? patients.filter((p) => p.patient_id.toLowerCase().includes(normalizedQuery))
    : patients;

  return (
    <Box sx={{ maxWidth: 960, mx: "auto", p: 3 }}>
      <Typography variant="h4" sx={{ mb: 3 }}>
        Patients
      </Typography>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.5 }}>
        <TextField
          size="small"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by patient ID…"
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
              sx: { fontFamily: "var(--font-mono)" },
            },
          }}
          sx={{ minWidth: 260 }}
        />
        {query && (
          <Button variant="outlined" size="small" onClick={() => setQuery("")}>
            Clear
          </Button>
        )}
        <Button
          variant="outlined"
          size="small"
          startIcon={<RefreshIcon />}
          onClick={load}
        >
          Refresh
        </Button>
      </Stack>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        Showing {filteredPatients.length} of {patients.length} patients
      </Typography>

      {loading && (
        <Stack spacing={1}>
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} variant="rounded" height={64} />
          ))}
        </Stack>
      )}

      {!loading && filteredPatients.length > 0 && (
        <Virtuoso
          data={filteredPatients}
          useWindowScroll
          itemContent={(_index, p) => {
            const progress = Math.round((p.progress ?? 0) * 100);
            return (
              <Box sx={{ pb: 1 }}>
                <Card variant="outlined">
                  <CardActionArea onClick={() => router.push(`/patients/${p.patient_id}`)}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        p: 2,
                      }}
                    >
                      <Box>
                        <Typography variant="subtitle1" sx={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                          {p.patient_id}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {p.encounter_count} encounters
                        </Typography>
                      </Box>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={progress}
                          color={progress >= 100 ? "success" : "primary"}
                          sx={{ width: 120, height: 6, borderRadius: 1 }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          {p.reviewed_count ?? 0}/{p.encounter_count}
                        </Typography>
                      </Box>
                    </Box>
                  </CardActionArea>
                </Card>
              </Box>
            );
          }}
        />
      )}

      {!loading && patients.length === 0 && !error && (
        <Typography color="text.secondary" sx={{ textAlign: "center", py: 5 }}>
          No patients found. Process records to begin referral quality review.
        </Typography>
      )}
      {!loading && patients.length > 0 && filteredPatients.length === 0 && !error && (
        <Typography color="text.secondary" sx={{ textAlign: "center", py: 5 }}>
          No patients match your search. Try a different ID.
        </Typography>
      )}
    </Box>
  );
}
