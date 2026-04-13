import { useMemo } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { parseEntities, truncate } from "./goldDatasetUtils";
import type { SimilarCandidateItem } from "./goldDatasetTypes";

interface Props {
  open: boolean;
  candidates: SimilarCandidateItem[];
  selected: Record<string, boolean>;
  loading: boolean;
  onClose: () => void;
  onToggle: (candidateId: string, checked: boolean) => void;
  onApply: () => void;
}

export default function SimilarCandidatesBatch({
  open,
  candidates,
  selected,
  loading,
  onClose,
  onToggle,
  onApply,
}: Props) {
  const selectedCount = useMemo(
    () => candidates.filter((c) => selected[c.candidate_id]).length,
    [candidates, selected],
  );

  return (
    <Dialog open={open} onClose={() => !loading && onClose()} maxWidth="lg" fullWidth>
      <DialogTitle>Apply to similar candidates</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Alert severity="info">
            Review similar rows, untick any mismatches, then mark selected rows as gold.
          </Alert>
          <Box sx={{ maxHeight: 420, overflowY: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox" />
                  <TableCell>Candidate</TableCell>
                  <TableCell>Encounter text</TableCell>
                  <TableCell>Entities</TableCell>
                  <TableCell align="right">Similarity</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {candidates.map((item) => {
                  const entities = parseEntities(item.entities_json);
                  return (
                    <TableRow key={item.candidate_id} hover>
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={Boolean(selected[item.candidate_id])}
                          onChange={(event) => onToggle(item.candidate_id, event.target.checked)}
                          disabled={loading}
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                          {item.candidate_id}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{truncate(item.text, 180)}</Typography>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                          {entities.slice(0, 3).map((entity, index) => (
                            <Chip
                              key={`${entity.text}-${index}`}
                              size="small"
                              label={entity.snomed_term || entity.text}
                              color={entity.snomed_concept_id ? "primary" : "warning"}
                              variant="outlined"
                            />
                          ))}
                          {entities.length > 3 && (
                            <Chip size="small" label={`+${entities.length - 3} more`} variant="outlined" />
                          )}
                        </Stack>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="caption">
                          {Math.round((item.similarity || 0) * 100)}%
                        </Typography>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={loading}>
          Skip
        </Button>
        <Button variant="contained" onClick={onApply} disabled={loading || selectedCount < 1}>
          {loading ? "Applying..." : `Mark ${selectedCount} as gold`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
