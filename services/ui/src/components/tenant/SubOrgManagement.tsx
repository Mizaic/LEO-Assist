/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CBE90D5D
 *   DI: DI-982CC3AD
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CBE90D5D")
 */
"use client";

/**
 * Sub-Organisation Management
 *
 * Lets org admins onboard child organisations via the POST /onboard saga
 * (full ODS validation, Practitioner creation, invite email, subscription).
 *
 * Platform admins see the full org list from OrgManagement; this panel
 * is intended for the delegated "Sub-Organisations" tab in the portal.
 */

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import {
  listOrgs,
  onboardOrg,
  type Org,
  type OnboardRequest,
} from "@/lib/api/admin";
import { useAuth } from "@/lib/authContext";

interface Props {
  isPlatformAdmin: boolean;
}

const ORG_TYPE_LABELS: Record<string, string> = {
  gp: "GP Practice",
  pcn: "PCN",
  icb: "ICB",
  alliance: "Cancer Alliance",
};

export default function SubOrgManagement({ isPlatformAdmin }: Props) {
  const { session } = useAuth();
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [orgType, setOrgType] = useState<"gp" | "pcn" | "icb" | "alliance">("gp");
  const [orgName, setOrgName] = useState("");
  const [odsCode, setOdsCode] = useState("");
  const [parentOrgId, setParentOrgId] = useState("");
  const [givenName, setGivenName] = useState("");
  const [familyName, setFamilyName] = useState("");
  const [email, setEmail] = useState("");
  const [jobTitle, setJobTitle] = useState("");

  const callerOrg = session?.organizations?.[0];

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const all = await listOrgs();
      // For org admins, the list is already scoped by the API; show everything returned.
      // For platform admins, show all sub-orgs (the full list).
      setOrgs(all);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load organisations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetForm = () => {
    setOrgType("gp");
    setOrgName("");
    setOdsCode("");
    setParentOrgId("");
    setGivenName("");
    setFamilyName("");
    setEmail("");
    setJobTitle("");
  };

  const handleSubmit = async () => {
    if (!orgName.trim() || !odsCode.trim() || !email.trim() || !givenName.trim() || !familyName.trim()) {
      setError("Please fill in all required fields.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body: OnboardRequest = {
        organisation: {
          name: orgName.trim(),
          type: orgType,
          ods_code: odsCode.trim().toUpperCase(),
          parent_org_id: parentOrgId || callerOrg?.id || undefined,
        },
        primary_user: {
          email: email.trim().toLowerCase(),
          given_name: givenName.trim(),
          family_name: familyName.trim(),
          job_title: jobTitle.trim() || undefined,
        },
      };
      const result = await onboardOrg(body);
      setSuccess(result.message);
      setOpen(false);
      resetForm();
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Onboarding failed. Please check the ODS code and try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Sub-Organisations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isPlatformAdmin
              ? "All organisations in the system."
              : `Organisations within ${callerOrg?.name ?? "your hierarchy"}.`}
          </Typography>
        </Box>
        <Button
          startIcon={<AddIcon />}
          variant="contained"
          size="small"
          onClick={() => { setOpen(true); setError(null); setSuccess(null); }}
        >
          Onboard sub-organisation
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress />
        </Box>
      ) : orgs.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 6, color: "text.secondary" }}>
          <Typography>No sub-organisations yet. Use the button above to onboard one.</Typography>
        </Box>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.78rem", color: "text.secondary" } }}>
              <TableCell>Name</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>ODS Code</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>ODS Sync</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {orgs.map((o) => (
              <TableRow key={o.id} hover sx={{ "&:last-child td": { border: 0 } }}>
                <TableCell sx={{ fontWeight: 500 }}>{o.name}</TableCell>
                <TableCell>
                  <Chip
                    label={ORG_TYPE_LABELS[o.type] ?? o.type}
                    size="small"
                    variant="outlined"
                  />
                </TableCell>
                <TableCell sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                  {o.odsCode || "-"}
                </TableCell>
                <TableCell>
                  {o.onboarding_status === "active" ? (
                    <Chip label="Active" color="success" size="small" icon={<CheckCircleOutlineIcon />} />
                  ) : o.onboarding_status === "pending" ? (
                    <Chip label="Pending setup" color="warning" size="small" />
                  ) : (
                    <Chip label={o.onboarding_status ?? "—"} size="small" />
                  )}
                </TableCell>
                <TableCell>
                  {o.ods_sync_status === "mismatch" && (
                    <Tooltip title="ODS data differs — review required">
                      <Chip label="Mismatch" color="warning" size="small" icon={<WarningAmberIcon />} />
                    </Tooltip>
                  )}
                  {o.ods_sync_status === "closed" && (
                    <Tooltip title="ODS reports inactive — review required">
                      <Chip label="ODS Inactive" color="error" size="small" icon={<WarningAmberIcon />} />
                    </Tooltip>
                  )}
                  {(!o.ods_sync_status || o.ods_sync_status === "ok") && (
                    <Typography variant="caption" color="text.disabled">—</Typography>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {/* Onboarding dialog */}
      <Dialog open={open} onClose={() => { setOpen(false); resetForm(); }} maxWidth="sm" fullWidth>
        <DialogTitle>Onboard a Sub-Organisation</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Provide the ODS code and primary contact. LEO will validate the organisation
            with NHS ODS and send an invite to the primary user to complete setup.
          </Typography>

          <Typography variant="subtitle2" sx={{ mb: 1 }}>Organisation details</Typography>

          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>Type</InputLabel>
            <Select
              value={orgType}
              label="Type"
              onChange={(e) => setOrgType(e.target.value as typeof orgType)}
            >
              <MenuItem value="gp">GP Practice</MenuItem>
              <MenuItem value="pcn">PCN (Primary Care Network)</MenuItem>
              <MenuItem value="icb">ICB (Integrated Care Board)</MenuItem>
              <MenuItem value="alliance">Cancer Alliance</MenuItem>
            </Select>
          </FormControl>

          <TextField
            fullWidth label="Organisation name *" size="small" sx={{ mb: 2 }}
            value={orgName} onChange={(e) => setOrgName(e.target.value)}
          />
          <TextField
            fullWidth label="ODS code *" size="small" sx={{ mb: 2 }}
            helperText="NHS ODS code, e.g. C84065. Will be validated against the live ODS FHIR API."
            value={odsCode} onChange={(e) => setOdsCode(e.target.value.toUpperCase())}
          />

          {isPlatformAdmin && (
            <TextField
              fullWidth label="Parent organisation ID (optional)" size="small" sx={{ mb: 2 }}
              helperText="Leave blank to create a top-level organisation."
              value={parentOrgId} onChange={(e) => setParentOrgId(e.target.value)}
            />
          )}

          <Typography variant="subtitle2" sx={{ mb: 1, mt: 1 }}>Primary contact</Typography>
          <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
            <TextField
              fullWidth label="First name *" size="small"
              value={givenName} onChange={(e) => setGivenName(e.target.value)}
            />
            <TextField
              fullWidth label="Last name *" size="small"
              value={familyName} onChange={(e) => setFamilyName(e.target.value)}
            />
          </Box>
          <TextField
            fullWidth label="Work email *" size="small" sx={{ mb: 2 }}
            helperText="This person will receive an invite and become the organisation admin."
            value={email} onChange={(e) => setEmail(e.target.value)}
          />
          <TextField
            fullWidth label="Job title (optional)" size="small"
            value={jobTitle} onChange={(e) => setJobTitle(e.target.value)}
          />

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setOpen(false); resetForm(); }}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={submitting || !orgName.trim() || !odsCode.trim() || !email.trim() || !givenName.trim() || !familyName.trim()}
          >
            {submitting ? "Onboarding…" : "Onboard organisation"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
