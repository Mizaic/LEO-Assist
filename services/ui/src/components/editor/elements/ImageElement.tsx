'use client';

import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import ImageOutlined from '@mui/icons-material/ImageOutlined';
import { ImageElement as ImageElementType } from '@/lib/types/layout';

interface ImageElementProps {
  element: ImageElementType;
}

export function ImageElement({ element }: ImageElementProps) {
  if (!element.src) {
    return (
      <Box
        sx={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
          bgcolor: 'grey.200',
          border: 1,
          borderColor: 'divider',
          borderRadius: 0.5,
        }}
      >
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'text.disabled',
            gap: '8px',
            padding: '16px',
            textAlign: 'center',
          }}
        >
          <ImageOutlined sx={{ fontSize: '32px' }} />
          <Typography sx={{ fontSize: '0.625rem' }}>
            No image selected.
            <br />
            Set URL in properties.
          </Typography>
        </Box>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden',
        bgcolor: 'grey.200',
        border: 1,
        borderColor: 'divider',
        borderRadius: 0.5,
      }}
    >
      <Box
        component="img"
        src={element.src}
        alt={element.alt || 'Image'}
        sx={{ maxWidth: '100%', maxHeight: '100%' }}
        style={{
          objectFit: element.objectFit || 'contain',
          width: '100%',
          height: '100%',
        }}
      />
    </Box>
  );
}
