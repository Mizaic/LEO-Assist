"use client";

/**
 * /admin/guidance/test-patients -- the central library page.
 *
 * Lets reviewers:
 *   - filter by guideline (or "all")
 *   - build a single test patient (Build Patient dialog)
 *   - generate happy/fail/boundary patients across rule, guideline, or all (Generate dialog)
 *   - replay every patient in scope and view the regression report
 *
 * Design Controls: DI-LEO-AI-164 / 165 / 166.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import MenuItem from "@mui/material/MenuItem";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import BuildPatientDialog from "./BuildPatientDialog";
import GeneratePatientsDialog from "./GeneratePatientsDialog";
import ReplayResultsDialog from "./ReplayResultsDialog";
import {
  deletePatient,
  listGuidelines,
  listPatients,
  replay,
} from "./api";
import type {
  GuidelinePickerEntry,
  ReplayReport,
  TestPatient,
} from "./types";

const ALL = "__all__";

export default function TestPatientLibraryPage() {
  const [guidelines, setGuidelines] = useState<GuidelinePickerEntry[]>([]);
  const [scopeGuideline, setScopeGuideline] = useState<string>(ALL);
  const [patients, setPatients] = useState<TestPatient[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openBuild, setOpenBuild] = useState(false);
  const [openGenerate, setOpenGenerate] = useState(false);
  const [openReplay, setOpenReplay] = useState(false);
  const [replayReport, setReplayReport] = useState<ReplayReport | null>(null);
  const [running, setRunning] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    listGuidelines()
      .then(setGuidelines)
      .catch(() => setGuidelines([]));
  }, []);

  const fetchPatients = useCallback(() => {
    setLoading(true);
    setError(null);
    listPatients({
      guideline_id: scopeGuideline === ALL ? undefined : scopeGuideline,
    })
      .then(setPatients)
      .catch(() =>
        setError("Could not load saved patients. Please refresh the page.")
      )
      .finally(() => setLoading(false));
  }, [scopeGuideline]);

  useEffect(() => {
    fetchPatients();
  }, [fetchPatients, refreshKey]);

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deletePatient(id);
        setRefreshKey((n) => n + 1);
      } catch {
        setError("Could not delete that patient. Please try again.");
      }
    },
    []
  );

  const handleReplay = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const report = await replay({
        guideline_id: scopeGuideline === ALL ? undefined : scopeGuideline,
        scope_type: scopeGuideline === ALL ? "global" : "guideline",
        scope_id: scopeGuideline === ALL ? "default" : scopeGuideline,
        persist_report: true,
      });
      setReplayReport(report);
      setOpenReplay(true);
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Could not run the replay."
      );
    } finally {
      setRunning(false);
    }
  }, [scopeGuideline]);

  const buildGuidelineId =
    scopeGuideline === ALL ? guidelines[0]?.id || "" : scopeGuideline;

  const summary = useMemo(() => {
    const total = patients.length;
    const generated = patients.filter(
      (p) => p.generation_source === "generated"
    ).length;
    const expectations = patients.reduce(
      (acc, p) => acc + (p.expectations?.length || 0),
      0
    );
    return { total, generated, expectations };
  }, [patients]);

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Stack spacing={2}>
        <Box>
          <Typography variant="h5" component="h1">
            Test patients
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Saved patients are replayed every time the lookup index is
            rebuilt, so you catch any rule that quietly changes.
          </Typography>
        </Box>

        <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems={{ md: "center" }}>
          <TextField
            select
            size="small"
            label="Guideline"
            value={scopeGuideline}
            onChange={(e) => setScopeGuideline(e.target.value)}
            sx={{ minWidth: 280 }}
          >
            <MenuItem value={ALL}>All guidelines</MenuItem>
            {guidelines.map((g) => (
              <MenuItem key={g.id} value={g.id}>
                {g.title}
              </MenuItem>
            ))}
          </TextField>

          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              onClick={() => setOpenBuild(true)}
              disabled={!buildGuidelineId}
            >
              Build a patient
            </Button>
            <Button variant="outlined" onClick={() => setOpenGenerate(true)}>
              Generate patients
            </Button>
            <Button
              variant="outlined"
              color="success"
              onClick={handleReplay}
              disabled={running || patients.length === 0}
              startIcon={running ? <CircularProgress size={16} /> : undefined}
            >
              {running ? "Replaying..." : "Replay scope"}
            </Button>
          </Stack>
        </Stack>

        <Stack direction="row" spacing={2}>
          <Chip label={`${summary.total} saved`} />
          <Chip label={`${summary.generated} generated`} variant="outlined" />
          <Chip
            label={`${summary.expectations} expectation${summary.expectations === 1 ? "" : "s"}`}
            variant="outlined"
          />
        </Stack>

        {error && <Alert severity="error">{error}</Alert>}

        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress />
          </Box>
        ) : patients.length === 0 ? (
          <Alert severity="info">
            No saved patients yet. Build one or use Generate to create a
            starter set from the rule logic.
          </Alert>
        ) : (
          <TableContainer>
            <Table size="small" aria-label="Saved test patients">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Guideline</TableCell>
                  <TableCell>Codes</TableCell>
                  <TableCell>Age / sex</TableCell>
                  <TableCell>Expectations</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {patients.map((p) => (
                  <TableRow key={p.id} hover>
                    <TableCell>
                      <Typography variant="body2">{p.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {p.id}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" noWrap>
                        {p.guideline_title || p.guideline_id}
                      </Typography>
                    </TableCell>
                    <TableCell>{p.codes?.length || 0}</TableCell>
                    <TableCell>
                      {p.age != null ? `${p.age}y` : "-"} / {p.sex || "-"}
                    </TableCell>
                    <TableCell>{p.expectations?.length || 0}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={p.generation_source}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        color="error"
                        onClick={() => handleDelete(p.id)}
                      >
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Stack>

      {openBuild && (
        <BuildPatientDialog
          open={openBuild}
          onClose={() => setOpenBuild(false)}
          guidelineId={buildGuidelineId}
          onSaved={() => {
            setOpenBuild(false);
            setRefreshKey((n) => n + 1);
          }}
        />
      )}

      <GeneratePatientsDialog
        open={openGenerate}
        onClose={() => setOpenGenerate(false)}
        guidelineId={scopeGuideline === ALL ? undefined : scopeGuideline}
        onSaved={(count) => {
          if (count > 0) setRefreshKey((n) => n + 1);
        }}
      />

      <ReplayResultsDialog
        open={openReplay}
        onClose={() => setOpenReplay(false)}
        report={replayReport}
        patients={patients}
      />
    </Box>
  );
}
