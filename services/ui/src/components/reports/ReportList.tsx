'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import Select from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import FormControl from '@mui/material/FormControl';
import Table from '@mui/material/Table';
import TableHead from '@mui/material/TableHead';
import TableBody from '@mui/material/TableBody';
import TableRow from '@mui/material/TableRow';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import Paper from '@mui/material/Paper';
import Chip from '@mui/material/Chip';
import Checkbox from '@mui/material/Checkbox';
import CircularProgress from '@mui/material/CircularProgress';
import Typography from '@mui/material/Typography';
import Menu from '@mui/material/Menu';
import IconButton from '@mui/material/IconButton';
import Dialog from '@mui/material/Dialog';
import DialogTitle from '@mui/material/DialogTitle';
import DialogContent from '@mui/material/DialogContent';
import DialogActions from '@mui/material/DialogActions';
import InputAdornment from '@mui/material/InputAdornment';
import AddOutlined from '@mui/icons-material/AddOutlined';
import SearchOutlined from '@mui/icons-material/SearchOutlined';
import MoreHorizOutlined from '@mui/icons-material/MoreHorizOutlined';
import EditOutlined from '@mui/icons-material/EditOutlined';
import DeleteOutlined from '@mui/icons-material/DeleteOutlined';
import VisibilityOutlined from '@mui/icons-material/VisibilityOutlined';
import { getMeasureReports, deleteMeasureReport } from '@/lib/api/measureReports';
import type { MeasureReport } from '@/lib/types/fhir';

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  ...[
    { value: 'complete', label: 'Complete' },
    { value: 'error', label: 'Error' },
    { value: 'pending', label: 'Pending' },
  ].sort((a, b) => a.label.localeCompare(b.label, 'en', { sensitivity: 'base' })),
];

export function ReportList() {
  const router = useRouter();
  const [reports, setReports] = useState<MeasureReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [reportToDelete, setReportToDelete] = useState<MeasureReport | null>(null);
  const [deleteMode, setDeleteMode] = useState<'single' | 'bulk'>('single');
  const [selectedReportIds, setSelectedReportIds] = useState<string[]>([]);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuReport, setMenuReport] = useState<MeasureReport | null>(null);

  useEffect(() => { loadReports(); }, [statusFilter]);

  useEffect(() => {
    const validIds = new Set(reports.map((r) => r.id).filter(Boolean) as string[]);
    setSelectedReportIds((prev) => prev.filter((id) => validIds.has(id)));
  }, [reports]);

  const loadReports = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      const bundle = await getMeasureReports(params);
      const resources = bundle.entry?.map((e) => e.resource).filter(Boolean) as MeasureReport[] || [];
      setReports(resources);
    } catch {
      setReports([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    try {
      if (deleteMode === 'single') {
        if (!reportToDelete?.id) return;
        await deleteMeasureReport(reportToDelete.id);
      } else {
        if (selectedReportIds.length === 0) return;
        await Promise.all(selectedReportIds.map((id) => deleteMeasureReport(id)));
        setSelectedReportIds([]);
      }
      setDeleteDialogOpen(false);
      setReportToDelete(null);
      loadReports();
    } catch (error) {
      console.error('Failed to delete report:', error);
    }
  };

  const handleMenuClose = () => { setMenuAnchor(null); setMenuReport(null); };

  const getStatusChip = (status: string) => {
    const colorMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
      complete: 'success', pending: 'warning', error: 'error',
    };
    return <Chip label={status} color={colorMap[status] || 'info'} size="small" sx={{ textTransform: 'capitalize' }} />;
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return '-';
    try { return new Date(dateString).toLocaleDateString(); } catch { return dateString; }
  };

  const getMeasureName = (report: MeasureReport): string =>
    report.measure?.replace('Measure/', '') || 'Unknown';

  const allReportIds = reports.map((r) => r.id).filter(Boolean) as string[];
  const selectedCount = selectedReportIds.length;
  const allSelected = selectedCount > 0 && selectedCount === allReportIds.length;
  const someSelected = selectedCount > 0 && !allSelected;

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>Reports</Typography>
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
          <Button variant="outlined" startIcon={<DeleteOutlined />} disabled={selectedReportIds.length === 0}
            onClick={() => { setDeleteMode('bulk'); setReportToDelete(null); setDeleteDialogOpen(true); }}
          >
            Delete selected
          </Button>
          <Button variant="contained" startIcon={<AddOutlined />} onClick={() => router.push('/reports/new/edit')}>
            Create Report
          </Button>
        </Box>
      </Box>

      <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
        <TextField sx={{ width: 300 }} placeholder="Search reports..." size="small" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchOutlined /></InputAdornment> }}
        />
        <FormControl size="small" sx={{ width: 150 }}>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as string)} displayEmpty>
            {STATUS_OPTIONS.map((opt) => <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>)}
          </Select>
        </FormControl>
      </Box>

      <Paper sx={{ borderRadius: 1, overflow: 'hidden', bgcolor: 'background.paper' }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 6 }}><CircularProgress aria-label="Loading" /></Box>
        ) : reports.length === 0 ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 6, color: 'text.secondary' }}>
            <Typography>No reports found</Typography>
            <Button variant="contained" startIcon={<AddOutlined />} sx={{ mt: 2 }} onClick={() => router.push('/reports/new/edit')}>
              Create your first report
            </Button>
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 44 }}>
                    <Checkbox checked={allSelected} indeterminate={someSelected}
                      onChange={(e) => setSelectedReportIds(e.target.checked ? allReportIds : [])}
                      aria-label="Select all reports"
                    />
                  </TableCell>
                  <TableCell>ID</TableCell>
                  <TableCell>Measure</TableCell>
                  <TableCell>Period</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Date</TableCell>
                  <TableCell sx={{ width: 60 }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {reports.map((report) => (
                  <TableRow key={report.id}>
                    <TableCell>
                      <Checkbox checked={selectedReportIds.includes(report.id ?? '')} disabled={!report.id}
                        onChange={(e) => {
                          const rid = report.id;
                          if (!rid) return;
                          setSelectedReportIds((prev) => e.target.checked ? [...prev, rid] : prev.filter((id) => id !== rid));
                        }}
                        aria-label={`Select report ${report.id}`}
                      />
                    </TableCell>
                    <TableCell><strong>{report.id}</strong></TableCell>
                    <TableCell>{getMeasureName(report)}</TableCell>
                    <TableCell>{formatDate(report.period?.start)} - {formatDate(report.period?.end)}</TableCell>
                    <TableCell>{getStatusChip(report.status)}</TableCell>
                    <TableCell>{formatDate(report.date)}</TableCell>
                    <TableCell>
                      <IconButton aria-label="Report actions" size="small" onClick={(e) => { setMenuAnchor(e.currentTarget); setMenuReport(report); }}>
                        <MoreHorizOutlined />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>

      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={handleMenuClose}>
        <MenuItem onClick={() => { router.push(`/reports/${menuReport?.id}`); handleMenuClose(); }}>
          <VisibilityOutlined sx={{ mr: 1 }} fontSize="small" /> View
        </MenuItem>
        <MenuItem onClick={() => { router.push(`/reports/${menuReport?.id}/edit`); handleMenuClose(); }}>
          <EditOutlined sx={{ mr: 1 }} fontSize="small" /> Edit
        </MenuItem>
        <MenuItem onClick={() => {
          if (menuReport) { setDeleteMode('single'); setReportToDelete(menuReport); setDeleteDialogOpen(true); }
          handleMenuClose();
        }}>
          <DeleteOutlined sx={{ mr: 1 }} fontSize="small" /> Delete
        </MenuItem>
      </Menu>

      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>{deleteMode === 'bulk' ? 'Delete Reports' : 'Delete Report'}</DialogTitle>
        <DialogContent>
          {deleteMode === 'bulk'
            ? `Are you sure you want to delete ${selectedReportIds.length} reports? This action cannot be undone.`
            : `Are you sure you want to delete report "${reportToDelete?.id}"? This action cannot be undone.`}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>Delete</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
