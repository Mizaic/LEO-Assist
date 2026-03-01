'use client';

import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import Autocomplete from '@mui/material/Autocomplete';
import FormControl from '@mui/material/FormControl';
import FormLabel from '@mui/material/FormLabel';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import CodeOutlined from '@mui/icons-material/CodeOutlined';
import { getLibraries, getLibrary } from '@/lib/api';
import type { Library } from '@/lib/types/fhir';

interface LibraryPickerProps {
  value: string;
  onChange: (libraryId: string) => void;
}

export function LibraryPicker({ value, onChange }: LibraryPickerProps) {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [loading, setLoading] = useState(true);
  const [queryPreview, setQueryPreview] = useState<string>('');

  useEffect(() => {
    loadLibraries();
  }, []);

  useEffect(() => {
    if (value) {
      loadLibraryDetails(value);
    } else {
      setQueryPreview('');
    }
  }, [value]);

  const loadLibraries = async () => {
    setLoading(true);
    try {
      const bundle = await getLibraries({ status: 'active' });
      const resources = bundle.entry?.map((e) => e.resource).filter(Boolean) as Library[] || [];
      setLibraries(resources);
    } catch {
      setLibraries([]);
    } finally {
      setLoading(false);
    }
  };

  const loadLibraryDetails = async (libraryId: string) => {
    try {
      const library = await getLibrary(libraryId);
      const cypherContent = library.content?.find(
        (c) => c.title === 'cypher' || c.contentType === 'text/plain'
      );
      if (cypherContent?.data) {
        try {
          setQueryPreview(atob(cypherContent.data));
        } catch {
          setQueryPreview('(Unable to decode query)');
        }
      } else {
        setQueryPreview('(No query content)');
      }
    } catch {
      setQueryPreview('(Failed to load query)');
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 1.5 }}>
        <CircularProgress size={16} />
        <Typography>Loading libraries...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <FormControl fullWidth>
        <FormLabel sx={{ mb: 0.5, fontSize: '0.875rem' }}>Linked Library</FormLabel>
        <Autocomplete
          options={libraries}
          getOptionLabel={(lib) => lib.title || lib.name || lib.id || ''}
          value={libraries.find((lib) => lib.id === value) || null}
          onChange={(_, newValue) => onChange(newValue?.id || '')}
          renderInput={(params) => (
            <TextField {...params} placeholder="Select a library..." size="small" />
          )}
          noOptionsText="No libraries available"
        />
      </FormControl>

      {value && queryPreview && (
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, color: 'text.secondary', fontSize: '0.75rem' }}>
            <CodeOutlined fontSize="small" />
            <span>Query Preview</span>
          </Box>
          <Box
            sx={{
              p: 1.5,
              bgcolor: 'grey.200',
              borderRadius: 1,
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              maxHeight: 200,
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
            }}
          >
            {queryPreview}
          </Box>
        </Box>
      )}

      {!value && (
        <Typography sx={{ p: 1.5, color: 'text.disabled', fontSize: '0.75rem' }}>
          Select a library to see its query definition
        </Typography>
      )}
    </Box>
  );
}
