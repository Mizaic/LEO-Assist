/**
 * Notice on a paused extraction when the form was not recognised, or the
 * form check could not run.
 *
 * Atlas trace: UN-AF530E8E -> DI-E21DF9EF -> DO-E458EEC5 -> VT-B13F7C48
 */
"use client";

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import SchoolIcon from "@mui/icons-material/School";

import {
  FORM_CHECK_FAILED_COPY,
  FORM_NOT_RECOGNISED_COPY,
  NO_CLOSE_FORM_COPY,
} from "./extractionReviewCopy";
import {
  closestFormLine,
  missingHeadingsLine,
  toRecognitionRows,
  type RecognitionRow,
} from "./formRecognitionRows";

interface Props {
  rows: unknown;
  onTeach: () => void;
}

export default function FormRecognitionNotice({ rows, onTeach }: Props) {
  const all = toRecognitionRows(rows);
  const unrecognised = all.filter((row) => row.outcome === "unrecognised");
  const failed = all.some((row) => row.outcome === "recognition_failed");
  if (!unrecognised.length && !failed) return null;
  return (
    <Stack spacing={1} sx={{ px: 2, pt: 1.5, flexShrink: 0 }} data-testid="form-recognition-notice">
      {failed ? <Alert severity="error">{FORM_CHECK_FAILED_COPY}</Alert> : null}
      {unrecognised.length ? (
        <Alert
          severity="warning"
          action={
            <Button
              size="small"
              variant="contained"
              color="primary"
              startIcon={<SchoolIcon />}
              onClick={onTeach}
            >
              Teach this form
            </Button>
          }
        >
          <Typography variant="body2" fontWeight={700}>
            {FORM_NOT_RECOGNISED_COPY}
          </Typography>
          {unrecognised.map((row, idx) => (
            <UnrecognisedDetail key={`${row.title}-${idx}`} row={row} />
          ))}
        </Alert>
      ) : null}
    </Stack>
  );
}

function UnrecognisedDetail({ row }: { row: RecognitionRow }) {
  const missing = row.best ? missingHeadingsLine(row.best.missing) : "";
  return (
    <Stack spacing={0.25} sx={{ mt: 0.5 }}>
      {row.title ? (
        <Typography variant="body2" fontWeight={600}>
          {row.title}
        </Typography>
      ) : null}
      <Typography variant="body2">
        {row.best ? closestFormLine(row.best) : NO_CLOSE_FORM_COPY}
      </Typography>
      {missing ? <Typography variant="body2">{missing}</Typography> : null}
    </Stack>
  );
}
