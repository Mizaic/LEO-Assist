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
import { getMeasures, deleteMeasure } from '@/lib/api';
import type { Measure } from '@/lib/types/fhir';

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  ...[
    { value: 'active', label: 'Active' },
    { value: 'draft', label: 'Draft' },
    { value: 'retired', label: 'Retired' },
  ].sort((a, b) => a.label.localeCompare(b.label, 'en', { sensitivity: 'base' })),
];

export function MeasureList() {
  const router = useRouter();
  const [measures, setMeasures] = useState<Measure[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [measureToDelete, setMeasureToDelete] = useState<Measure | null>(null);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuMeasure, setMenuMeasure] = useState<Measure | null>(null);

  useEffect(() => {
    loadMeasures();
  }, [searchQuery, statusFilter]);

  const loadMeasures = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (searchQuery) params.name = searchQuery;
      if (statusFilter) params.status = statusFilter;
      const bundle = await getMeasures(params);
      const resources = bundle.entry?.map((e) => e.resource).filter(Boolean) as Measure[] || [];
      setMeasures(resources);
    } catch {
      setMeasures([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!measureToDelete?.id) return;
    try {
      await deleteMeasure(measureToDelete.id);
      setDeleteDialogOpen(false);
      setMeasureToDelete(null);
      loadMeasures();
    } catch (error) {
      console.error('Failed to delete measure:', error);
    }
  };

  const getStatusChip = (status: string) => {
    const colorMap: Record<string, 'success' | 'warning' | 'error' | 'info'> = {
      active: 'success', draft: 'warning', retired: 'error', unknown: 'info',
    };
    return <Chip label={status} color={colorMap[status] || 'info'} size="small" sx={{ textTransform: 'capitalize' }} />;
  };

  const getCategory = (measure: Measure): string => {
    return measure.topic?.[0]?.coding?.[0]?.code || 'Uncategorized';
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h5" component="h1" sx={{ fontWeight: 600 }}>Measures</Typography>
        <Button variant="contained" startIcon={<AddOutlined />} onClick={() => router.push('/measures/new')}>
          Create Measure
        </Button>
      </Box>

      <Box sx={{ display: 'flex', gap: 1.5, mb: 2 }}>
        <TextField
          sx={{ width: 300 }}
          placeholder="Search measures..."
          size="small"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          InputProps={{
            startAdornment: <InputAdornment position="start"><SearchOutlined /></InputAdornment>,
          }}
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
        ) : measures.length === 0 ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 6, color: 'text.secondary' }}>
            <Typography>No measures found</Typography>
            <Button variant="contained" startIcon={<AddOutlined />} sx={{ mt: 2 }} onClick={() => router.push('/measures/new')}>
              Create your first measure
            </Button>
          </Box>
        ) : (
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Title</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Library</TableCell>
                  <TableCell sx={{ width: 60 }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {measures.map((measure) => (
                  <TableRow key={measure.id}>
                    <TableCell><strong>{measure.title || measure.name || 'Untitled'}</strong></TableCell>
                    <TableCell>{getCategory(measure)}</TableCell>
                    <TableCell>{getStatusChip(measure.status)}</TableCell>
                    <TableCell>{measure.library?.[0]?.replace('Library/', '') || '-'}</TableCell>
                    <TableCell>
                      <IconButton aria-label="Measure actions" size="small" onClick={(e) => { setMenuAnchor(e.currentTarget); setMenuMeasure(measure); }}>
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

      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => { setMenuAnchor(null); setMenuMeasure(null); }}>
        <MenuItem onClick={() => { router.push(`/measures/${menuMeasure?.id}`); setMenuAnchor(null); }}>
          <VisibilityOutlined sx={{ mr: 1 }} fontSize="small" /> View
        </MenuItem>
        <MenuItem onClick={() => { router.push(`/measures/${menuMeasure?.id}`); setMenuAnchor(null); }}>
          <EditOutlined sx={{ mr: 1 }} fontSize="small" /> Edit
        </MenuItem>
        <MenuItem onClick={() => {
          if (menuMeasure) { setMeasureToDelete(menuMeasure); setDeleteDialogOpen(true); }
          setMenuAnchor(null); setMenuMeasure(null);
        }}>
          <DeleteOutlined sx={{ mr: 1 }} fontSize="small" /> Delete
        </MenuItem>
      </Menu>

      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Delete Measure</DialogTitle>
        <DialogContent>
          Are you sure you want to delete &quot;{measureToDelete?.title || measureToDelete?.name}&quot;? This action cannot be undone.
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" color="error" onClick={handleDelete}>Delete</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
