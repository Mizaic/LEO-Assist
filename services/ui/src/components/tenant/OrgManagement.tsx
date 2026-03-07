"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import InputAdornment from "@mui/material/InputAdornment";
import InputLabel from "@mui/material/InputLabel";
import MenuItem from "@mui/material/MenuItem";
import Pagination from "@mui/material/Pagination";
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
import SearchIcon from "@mui/icons-material/Search";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  createOrg,
  deleteOrg,
  listOrgs,
  type Org,
} from "@/lib/api/admin";
import ConfirmDialog from "@/components/ConfirmDialog";
import OrgDrawer from "./OrgDrawer";

// ------------------------------------------------------------------
// Type configuration - colour, label, tooltip
// ------------------------------------------------------------------

const ORG_TYPE_CONFIG: Record<
  string,
  { label: string; color: "success" | "info" | "secondary" | "default" | "warning"; tip: string }
> = {
  gp: {
    label: "GP Practice",
    color: "success",
    tip: "A GP practice that registers patients directly.",
  },
  pcn: {
    label: "PCN",
    color: "warning",
    tip: "Primary Care Network - a group of GP practices within an ICB.",
  },
  icb: {
    label: "ICB",
    color: "info",
    tip: "Integrated Care Board - oversees a group of GP practices and PCNs.",
  },
  alliance: {
    label: "Cancer Alliance",
    color: "secondary",
    tip: "A Cancer Alliance - covers a network of ICBs and practices.",
  },
  organization: {
    label: "Organisation",
    color: "default",
    tip: "A general organisation in the system.",
  },
};

const PAGE_SIZE = 20;

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export default function OrgManagement() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [page, setPage] = useState(1);

  const [addOpen, setAddOpen] = useState(false);
  const [addType, setAddType] = useState<"gp" | "icb" | "alliance" | "pcn">("gp");
  const [addName, setAddName] = useState("");
  const [addOds, setAddOds] = useState("");
  const [addParentId, setAddParentId] = useState("");
  const [addAllianceId, setAddAllianceId] = useState("");
  const [addSubmitting, setAddSubmitting] = useState(false);

  const [deleteConfirm, setDeleteConfirm] = useState<Org | null>(null);
  const [drawerOrg, setDrawerOrg] = useState<Org | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOrgs(await listOrgs());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load organisations. Please try again.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Filter + search
  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return orgs.filter((o) => {
      const matchType = typeFilter === "all" || o.type === typeFilter;
      const matchSearch =
        !q ||
        (o.name || "").toLowerCase().includes(q) ||
        (o.odsCode || "").toLowerCase().includes(q) ||
        (o.parent_name || "").toLowerCase().includes(q);
      return matchType && matchSearch;
    });
  }, [orgs, search, typeFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // Reset page when filter changes
  const handleSearch = (v: string) => { setSearch(v); setPage(1); };
  const handleTypeFilter = (v: string) => { setTypeFilter(v); setPage(1); };

  const handleAdd = async () => {
    if (!addName.trim()) return;
    setAddSubmitting(true);
    try {
      await createOrg({
        type: addType,
        name: addName.trim(),
        ods_code: addOds.trim() || undefined,
        parent_id: addType === "gp" && addParentId ? addParentId : undefined,
        alliance_id: addType === "icb" && addAllianceId ? addAllianceId : undefined,
      });
      setAddOpen(false);
      setAddName(""); setAddOds(""); setAddParentId(""); setAddAllianceId("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create organisation.");
    } finally {
      setAddSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirm) return;
    try {
      await deleteOrg(deleteConfirm.id);
      setDeleteConfirm(null);
      load();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not remove this organisation. It may still have patients linked to it."
      );
      setDeleteConfirm(null);
    }
  };

  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = { all: orgs.length };
    for (const o of orgs) counts[o.type] = (counts[o.type] || 0) + 1;
    return counts;
  }, [orgs]);

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 2 }}>
        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
            Organisations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            All GP practices, PCNs, ICBs, and Cancer Alliances in your system.{" "}
            <strong>{orgs.length}</strong> total.
          </Typography>
        </Box>
        <Button
          startIcon={<AddIcon />}
          variant="contained"
          size="small"
          onClick={() => setAddOpen(true)}
        >
          Add organisation
        </Button>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Filters */}
      <Box sx={{ display: "flex", gap: 1, mb: 2, flexWrap: "wrap" }}>
        <TextField
          size="small"
          placeholder="Search by name or ODS code..."
          value={search}
          onChange={(e) => handleSearch(e.target.value)}
          sx={{ minWidth: 260 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        {(["all", "gp", "pcn", "icb", "alliance", "organization"] as const).map((t) => (
          <Chip
            key={t}
            label={`${t === "all" ? "All" : ORG_TYPE_CONFIG[t]?.label ?? t} (${typeCounts[t] || 0})`}
            onClick={() => handleTypeFilter(t)}
            variant={typeFilter === t ? "filled" : "outlined"}
            color={t !== "all" ? ORG_TYPE_CONFIG[t]?.color : "default"}
            size="small"
            sx={{ cursor: "pointer" }}
          />
        ))}
      </Box>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : filtered.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 6, color: "text.secondary" }}>
          <Typography>No organisations match your search.</Typography>
        </Box>
      ) : (
        <>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.78rem", color: "text.secondary" } }}>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>ODS code</TableCell>
                <TableCell align="right">Patients</TableCell>
                <TableCell>Part of</TableCell>
                <TableCell>ODS Status</TableCell>
                <TableCell></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pageRows.map((o) => {
                const tc = ORG_TYPE_CONFIG[o.type] || ORG_TYPE_CONFIG.organization;
                const parentLabel = o.parent_name || o.alliance_name || "-";
                return (
                  <TableRow
                    key={o.id}
                    hover
                    onClick={() => setDrawerOrg(o)}
                    sx={{ "&:last-child td": { border: 0 }, cursor: "pointer" }}
                  >
                    <TableCell sx={{ fontWeight: 500 }}>{o.name}</TableCell>
                    <TableCell>
                      <Tooltip title={tc.tip} placement="top">
                        <Chip
                          label={tc.label}
                          color={tc.color}
                          size="small"
                          variant="outlined"
                        />
                      </Tooltip>
                    </TableCell>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                      {o.odsCode || "-"}
                    </TableCell>
                    <TableCell align="right">
                      {o.patient_count > 0 ? (
                        <Chip
                          label={o.patient_count.toLocaleString()}
                          size="small"
                          sx={{ fontSize: "0.75rem" }}
                        />
                      ) : (
                        <Typography variant="caption" color="text.disabled">0</Typography>
                      )}
                    </TableCell>
                    <TableCell sx={{ color: "text.secondary", fontSize: "0.82rem" }}>
                      {parentLabel}
                    </TableCell>
                    <TableCell>
                      {o.ods_sync_status === "mismatch" && (
                        <Tooltip title="ODS data differs from LEO record — review required">
                          <Chip label="Mismatch" color="warning" size="small" icon={<WarningAmberIcon />} />
                        </Tooltip>
                      )}
                      {o.ods_sync_status === "closed" && (
                        <Tooltip title="ODS reports this organisation as inactive — review required">
                          <Chip label="ODS Inactive" color="error" size="small" icon={<WarningAmberIcon />} />
                        </Tooltip>
                      )}
                      {o.ods_sync_status === "error" && (
                        <Tooltip title="ODS sync encountered an error for this org">
                          <Chip label="Sync error" color="default" size="small" />
                        </Tooltip>
                      )}
                    </TableCell>
                    <TableCell align="right" onClick={(e) => e.stopPropagation()}>
                      {o.patient_count === 0 ? (
                        <Button
                          size="small"
                          color="error"
                          onClick={(e) => { e.stopPropagation(); setDeleteConfirm(o); }}
                          sx={{ minWidth: 0, fontSize: "0.75rem" }}
                        >
                          Remove
                        </Button>
                      ) : (
                        <Tooltip title="Cannot remove an organisation that has patients linked to it.">
                          <span>
                            <Button size="small" color="error" disabled sx={{ minWidth: 0, fontSize: "0.75rem" }}>
                              Remove
                            </Button>
                          </span>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>

          {totalPages > 1 && (
            <Box sx={{ display: "flex", justifyContent: "center", pt: 2 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_, v) => setPage(v)}
                size="small"
              />
            </Box>
          )}
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", textAlign: "center", mt: 1 }}>
            Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </Typography>
        </>
      )}

      {/* Add org dialog */}
      <Dialog open={addOpen} onClose={() => setAddOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add an organisation</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Choose the type of organisation and fill in its details. You can link it to a parent later.
          </Typography>
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>What type is it?</InputLabel>
            <Select
              value={addType}
              label="What type is it?"
              onChange={(e) => setAddType(e.target.value as "gp" | "icb" | "alliance" | "pcn")}
            >
              <MenuItem value="gp">GP Practice</MenuItem>
              <MenuItem value="pcn">PCN (Primary Care Network)</MenuItem>
              <MenuItem value="icb">ICB (Integrated Care Board)</MenuItem>
              <MenuItem value="alliance">Cancer Alliance</MenuItem>
            </Select>
          </FormControl>
          <TextField
            fullWidth
            label="Name"
            value={addName}
            onChange={(e) => setAddName(e.target.value)}
            size="small"
            sx={{ mb: 2 }}
          />
          <TextField
            fullWidth
            label="ODS code (optional)"
            helperText="The NHS code for this organisation, e.g. C84065."
            value={addOds}
            onChange={(e) => setAddOds(e.target.value)}
            size="small"
            sx={{ mb: 2 }}
          />
          {addType === "gp" && (
            <TextField
              fullWidth
              label="Parent ICB (optional — enter its ID)"
              value={addParentId}
              onChange={(e) => setAddParentId(e.target.value)}
              size="small"
            />
          )}
          {addType === "icb" && (
            <TextField
              fullWidth
              label="Cancer Alliance (optional — enter its ID)"
              value={addAllianceId}
              onChange={(e) => setAddAllianceId(e.target.value)}
              size="small"
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleAdd}
            disabled={addSubmitting || !addName.trim()}
          >
            {addSubmitting ? "Creating..." : "Create"}
          </Button>
        </DialogActions>
      </Dialog>

      {deleteConfirm && (
        <ConfirmDialog
          title="Remove organisation"
          body={`Remove "${deleteConfirm.name}" from the system? This cannot be undone.`}
          confirmLabel="Yes, remove it"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}

      <OrgDrawer
        org={drawerOrg}
        onClose={() => setDrawerOrg(null)}
        onChanged={() => {
          load();
          // Refresh drawer data with latest from reloaded list
          if (drawerOrg) {
            listOrgs().then((all) => {
              const updated = all.find((o) => o.id === drawerOrg.id);
              setDrawerOrg(updated ?? null);
            }).catch(() => {});
          }
        }}
      />
    </Box>
  );
}
