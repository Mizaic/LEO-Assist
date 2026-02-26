"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Grid from "@mui/material/Grid";
import Skeleton from "@mui/material/Skeleton";
import Chip from "@mui/material/Chip";
import AddIcon from "@mui/icons-material/Add";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import { fetchMeasures } from "@/lib/analyticsApi";

interface MeasureEntry {
  resource: Record<string, any>;
}

export default function ReportsPage() {
  const router = useRouter();
  const [measures, setMeasures] = useState<MeasureEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMeasures()
      .then((data) => setMeasures(data.entry ?? []))
      .catch(() => setMeasures([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5">Reports</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => router.push("/reports/builder")}
        >
          New Report
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
        Create and manage clinical audit reports using FHIR Measures.
        Each report evaluates one or more Measures and generates a MeasureReport.
      </Typography>

      {loading ? (
        <Grid container spacing={2}>
          {[0, 1, 2].map((i) => (
            <Grid key={i} size={{ xs: 12, sm: 6, md: 4 }}>
              <Skeleton variant="rectangular" height={140} sx={{ borderRadius: 3 }} />
            </Grid>
          ))}
        </Grid>
      ) : measures.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 6 }}>
          <DescriptionOutlinedIcon sx={{ fontSize: 48, color: "text.secondary", mb: 1 }} />
          <Typography color="text.secondary">
            No measures configured yet. Create your first measure to start building reports.
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={2}>
          {measures.map((m, i) => {
            const r = m.resource;
            return (
              <Grid key={r.id ?? i} size={{ xs: 12, sm: 6, md: 4 }}>
                <Card
                  sx={{ cursor: "pointer", "&:hover": { borderColor: "primary.main" } }}
                  onClick={() => router.push(`/reports/builder?measure=${r.id}`)}
                >
                  <CardContent>
                    <Typography variant="body1" sx={{ fontWeight: 600, mb: 0.5 }}>
                      {r.name ?? r.title ?? `Measure ${r.id}`}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                      {r.description ?? "No description"}
                    </Typography>
                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                      <Chip
                        label={r.status ?? "active"}
                        size="small"
                        color={r.status === "active" ? "success" : "default"}
                        sx={{ textTransform: "capitalize" }}
                      />
                      {r.url && (
                        <Chip label={r.url} size="small" variant="outlined" sx={{ fontSize: "0.7rem" }} />
                      )}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            );
          })}
        </Grid>
      )}
    </Box>
  );
}
