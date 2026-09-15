/**
 * Visible load failures for the EPR record. Fail closed -- never hide.
 *
 * Atlas trace:
 *   DO: DO-5D3EA371
 *   DI: DI-357A7468
 */

import Alert from "@mui/material/Alert";

interface Props {
  detailError: string | null;
  timelineError: string | null;
  entitiesError: string | null;
  showTimelineError: boolean;
}

export function RecordLoadAlerts({
  detailError,
  timelineError,
  entitiesError,
  showTimelineError,
}: Props) {
  return (
    <>
      {detailError && (
        <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
          {detailError}
        </Alert>
      )}
      {timelineError && showTimelineError && (
        <Alert severity="error" sx={{ mx: 2, mt: 1 }}>
          {timelineError}
        </Alert>
      )}
      {entitiesError && (
        <Alert severity="warning" sx={{ mx: 2, mt: 1 }}>
          {entitiesError}
        </Alert>
      )}
    </>
  );
}
