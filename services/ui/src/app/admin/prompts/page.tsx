"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import AddIcon from "@mui/icons-material/Add";
import { api } from "@/lib/api";

interface PromptConfig {
  id: string;
  name: string;
  version: number;
  verification: boolean;
  fewShotCount: number;
  updatedAt: string;
}

export default function PromptsPage() {
  const router = useRouter();
  const [prompts, setPrompts] = useState<PromptConfig[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ prompts: PromptConfig[] }>("/api/prompts")
      .then((data) => setPrompts(data.prompts || []))
      .catch(() => setPrompts([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
        <Typography variant="h5" fontWeight={600}>Prompt Management</Typography>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => router.push("/admin/prompts/new")}>
          New Prompt
        </Button>
      </Box>
      <TableContainer component={Paper} variant="outlined">
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Version</TableCell>
              <TableCell>Verification</TableCell>
              <TableCell>Few-shot Examples</TableCell>
              <TableCell>Last Updated</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={5}>Loading...</TableCell></TableRow>
            ) : prompts.length === 0 ? (
              <TableRow><TableCell colSpan={5}>No prompts configured.</TableCell></TableRow>
            ) : prompts.map((p) => (
              <TableRow key={p.id} hover sx={{ cursor: "pointer" }} onClick={() => router.push(`/admin/prompts/${p.id}`)}>
                <TableCell>{p.name}</TableCell>
                <TableCell>v{p.version}</TableCell>
                <TableCell>
                  <Chip label={p.verification ? "Enabled" : "Disabled"} size="small" color={p.verification ? "success" : "default"} />
                </TableCell>
                <TableCell>{p.fewShotCount}</TableCell>
                <TableCell>{p.updatedAt}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
