/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-158BE606
 *   DI: DI-2289D095
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-158BE606")
 */
"use client";

/**
 * Validation Lab -- single clinical testing experience.
 *
 * One flow: new test patient -> build profile -> add encounter(s) ->
 * create referral documentation -> submit referral (real pipeline run).
 * The former "Fixtures" (code-replay-only :TestPatient library) and
 * "Cases" split has been retired -- there is now one production-faithful
 * path.
 *
 * Atlas: UN-4DCE95C8 / DI-724CD8A5 / DI-2289D095 / DI-9138BAC9 / DI-A898556B
 * DO: DO-158BE606
 */

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import LabCasesPanel from "./LabCasesPanel";

export default function ValidationLabPage() {
  return (
    <Box sx={{ p: 3, maxWidth: 1200 }} data-testid="validation-lab-page">
      <Typography variant="h5" component="h1" sx={{ mb: 1 }}>
        Validation Lab
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        One place to test the clinical pipeline: build a test patient, add
        their history and referral, then submit it through the real
        pipeline and review the SBAR it produces.
      </Typography>
      <LabCasesPanel />
    </Box>
  );
}
