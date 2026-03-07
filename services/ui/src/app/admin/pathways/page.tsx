"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CardActionArea from "@mui/material/CardActionArea";
import Grid from "@mui/material/Grid";
import Chip from "@mui/material/Chip";
import AddIcon from "@mui/icons-material/Add";
import { api } from "@/lib/api";

interface PlanDefinition {
  id: string;
  name: string;
  status: string;
  description?: string;
  actionCount?: number;
}

export default function PathwaysPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<PlanDefinition[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ entry: Array<{ resource: PlanDefinition }> }>("/fhir/PlanDefinition")
      .then((data) => {
        setPlans((data.entry || []).map((e) => e.resource));
      })
      .catch(() => setPlans([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight={600}>Clinical Pathways</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => router.push("/admin/pathways/new")}>
          New Pathway
        </Button>
      </Box>
      {loading ? (
        <Typography color="text.secondary">Loading pathways...</Typography>
      ) : plans.length === 0 ? (
        <Typography color="text.secondary">No pathways configured yet. Create your first pathway to get started.</Typography>
      ) : (
        <Grid container spacing={2}>
          {plans.map((plan) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={plan.id}>
              <Card variant="outlined">
                <CardActionArea onClick={() => router.push(`/admin/pathways/${plan.id}`)}>
                  <CardContent>
                    <Typography variant="subtitle1" fontWeight={600}>{plan.name}</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      {plan.description || "No description"}
                    </Typography>
                    <Chip
                      label={plan.status}
                      size="small"
                      color={plan.status === "active" ? "success" : "default"}
                    />
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
