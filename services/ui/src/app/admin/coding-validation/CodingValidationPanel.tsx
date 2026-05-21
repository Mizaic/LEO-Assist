"use client";

import { useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Typography from "@mui/material/Typography";
import Stack from "@mui/material/Stack";
import CircularProgress from "@mui/material/CircularProgress";
import Alert from "@mui/material/Alert";
import Chip from "@mui/material/Chip";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid";

import { getCodingValidation, updateGroundTruth } from "./api";

export default function CodingValidationPanel() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  async function fetchData() {
    setLoading(true);
    try {
      const res = await getCodingValidation();
      setData(res);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const handleAction = async (caseId: string, surfaceForm: string, action: string) => {
    try {
      await updateGroundTruth(caseId, surfaceForm, action);
      await fetchData();
    } catch (err: any) {
      alert("Failed to update: " + err.message);
    }
  };

  if (loading) {
    return (
      <Box p={4} textAlign="center">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={4}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box>
      <Box mb={4}>
        <Typography variant="h5" gutterBottom>
          Clinical Coding Validation (VAL-41005BA4)
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Total Unique Terms: {data?.total_terms}
        </Typography>
      </Box>

      {data?.cases?.map((c: any) => (
        <Card key={c.case_id} sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Case: {c.case_id}
            </Typography>
            <Grid container spacing={2}>
              {c.facts?.map((fact: any, idx: number) => (
                <Grid item xs={12} md={6} lg={4} key={idx}>
                  <Card variant="outlined" sx={{ height: "100%", bgcolor: fact.safe_attached ? "success.50" : "error.50" }}>
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight="bold">
                        {fact.surface_form}
                      </Typography>
                      <Stack direction="row" spacing={1} my={1}>
                        <Chip size="small" label={fact.safe_attached ? "Safe Attached" : "Unresolved"} color={fact.safe_attached ? "success" : "error"} />
                        {fact.unresolved_reason && (
                          <Chip size="small" label={fact.unresolved_reason} variant="outlined" />
                        )}
                        {fact.expected_withhold && (
                          <Chip size="small" label="Expected Withhold" color="default" />
                        )}
                      </Stack>
                      <Typography variant="body2">
                        <strong>Concept:</strong> {fact.concept_id || "None"}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Term:</strong> {fact.preferred_term || "None"}
                      </Typography>
                      <Typography variant="body2">
                        <strong>Score:</strong> {fact.score}
                      </Typography>

                      <Box mt={2}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          Top Candidates:
                        </Typography>
                        {fact.top_candidates?.map((cand: any, i: number) => (
                          <Box key={i} sx={{ p: 1, mb: 1, bgcolor: "background.paper", borderRadius: 1, border: "1px solid", borderColor: "divider" }}>
                            <Typography variant="caption" display="block"><strong>{cand.term}</strong> ({cand.concept_id})</Typography>
                            <Typography variant="caption" display="block">Score: {cand.score} | Tag: {cand.semantic_tag}</Typography>
                          </Box>
                        ))}
                      </Box>

                      <Stack direction="row" spacing={1} mt={2}>
                        <Button size="small" variant="contained" color="primary" onClick={() => handleAction(c.case_id, fact.surface_form, "accept")}>
                          Accept
                        </Button>
                        <Button size="small" variant="outlined" color="error" onClick={() => handleAction(c.case_id, fact.surface_form, "remove")}>
                          Remove
                        </Button>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
