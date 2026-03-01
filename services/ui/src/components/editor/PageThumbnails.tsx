'use client';

import { useCallback, useState } from 'react';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Typography from '@mui/material/Typography';
import Tooltip from '@mui/material/Tooltip';
import AddOutlined from '@mui/icons-material/AddOutlined';
import MoreHorizOutlined from '@mui/icons-material/MoreHorizOutlined';
import DeleteOutlined from '@mui/icons-material/DeleteOutlined';
import ContentCopyOutlined from '@mui/icons-material/ContentCopyOutlined';
import CropPortraitOutlined from '@mui/icons-material/CropPortraitOutlined';
import CropLandscapeOutlined from '@mui/icons-material/CropLandscapeOutlined';
import ListItemIcon from '@mui/material/ListItemIcon';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useEditorStore } from '@/stores/editorStore';
import { LayoutPage, getPageDimensions } from '@/lib/types/layout';

const THUMBNAIL_WIDTH = 60;
const THUMBNAIL_PORTRAIT_HEIGHT = 85;
const THUMBNAIL_LANDSCAPE_HEIGHT = 42;

interface SortableThumbnailProps {
  page: LayoutPage;
  index: number;
  isSelected: boolean;
  onClick: () => void;
}

function SortableThumbnail({ page, index, isSelected, onClick }: SortableThumbnailProps) {
  const {
    deletePage,
    duplicatePage,
    setPageOrientation,
    layout,
  } = useEditorStore();

  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const menuOpen = Boolean(anchorEl);

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: page.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const isPortrait = page.orientation === 'portrait';
  const height = isPortrait ? THUMBNAIL_PORTRAIT_HEIGHT : THUMBNAIL_LANDSCAPE_HEIGHT;
  const width = THUMBNAIL_WIDTH;

  const handleDelete = useCallback(() => {
    if (layout.pages.length > 1) {
      deletePage(page.id);
    }
    setAnchorEl(null);
  }, [deletePage, page.id, layout.pages.length]);

  const handleDuplicate = useCallback(() => {
    duplicatePage(page.id);
    setAnchorEl(null);
  }, [duplicatePage, page.id]);

  const handleToggleOrientation = useCallback(() => {
    setPageOrientation(page.id, isPortrait ? 'landscape' : 'portrait');
    setAnchorEl(null);
  }, [setPageOrientation, page.id, isPortrait]);

  return (
    <Box
      ref={setNodeRef}
      style={style}
      sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}
      data-testid="page-thumbnail"
    >
      <Typography sx={{ fontSize: '0.625rem', color: 'text.disabled', width: '16px', textAlign: 'right', pt: 0.5 }}>
        {index + 1}
      </Typography>
      <Box
        sx={(theme) => ({
          bgcolor: '#fff',
          border: 1,
          borderColor: 'divider',
          borderRadius: 0.5,
          cursor: 'pointer',
          position: 'relative',
          overflow: 'hidden',
          transition: 'box-shadow 0.1s ease',
          boxShadow: isSelected
            ? `0 0 0 2px ${theme.palette.primary.main}`
            : 'none',
          '&:hover': {
            boxShadow: isSelected
              ? `0 0 0 2px ${theme.palette.primary.main}`
              : `0 0 0 1px ${theme.palette.primary.main}`,
          },
        })}
        style={{ width, height }}
        onClick={onClick}
        {...attributes}
        {...listeners}
      >
        <Box
          sx={{
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'text.disabled',
            fontSize: '0.625rem',
          }}
        >
          {page.elements.length > 0 ? `${page.elements.length} items` : 'Empty'}
        </Box>

        <Tooltip title={isPortrait ? 'Portrait' : 'Landscape'}>
          <Box sx={{ position: 'absolute', bottom: '2px', left: '2px', fontSize: '12px', color: 'text.disabled' }}>
            {isPortrait ? <CropPortraitOutlined fontSize="inherit" /> : <CropLandscapeOutlined fontSize="inherit" />}
          </Box>
        </Tooltip>

        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            setAnchorEl(e.currentTarget);
          }}
          sx={{
            position: 'absolute',
            top: '2px',
            right: '2px',
            p: 0,
            '& .MuiSvgIcon-root': { fontSize: '16px' },
          }}
        >
          <MoreHorizOutlined />
        </IconButton>

        <Menu
          anchorEl={anchorEl}
          open={menuOpen}
          onClose={() => setAnchorEl(null)}
          onClick={(e) => e.stopPropagation()}
        >
          <MenuItem onClick={handleDuplicate}>
            <ListItemIcon><ContentCopyOutlined fontSize="small" /></ListItemIcon>
            Duplicate
          </MenuItem>
          <MenuItem onClick={handleToggleOrientation}>
            <ListItemIcon>
              {isPortrait ? <CropLandscapeOutlined fontSize="small" /> : <CropPortraitOutlined fontSize="small" />}
            </ListItemIcon>
            {isPortrait ? 'Make Landscape' : 'Make Portrait'}
          </MenuItem>
          <MenuItem onClick={handleDelete} disabled={layout.pages.length <= 1}>
            <ListItemIcon><DeleteOutlined fontSize="small" /></ListItemIcon>
            Delete
          </MenuItem>
        </Menu>
      </Box>
    </Box>
  );
}

export function PageThumbnails() {
  const {
    layout,
    selectedPageId,
    setSelection,
    addPage,
    reorderPages,
  } = useEditorStore();

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 5,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;

      if (over && active.id !== over.id) {
        const oldIndex = layout.pages.findIndex((p) => p.id === active.id);
        const newIndex = layout.pages.findIndex((p) => p.id === over.id);
        reorderPages(oldIndex, newIndex);
      }
    },
    [layout.pages, reorderPages]
  );

  const handleThumbnailClick = useCallback(
    (pageId: string) => {
      setSelection(pageId, []);
    },
    [setSelection]
  );

  const handleAddPage = useCallback(() => {
    addPage('portrait');
  }, [addPage]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', p: 1.5, gap: 1 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
        <Typography
          data-testid="page-thumbnails-title"
          sx={{ fontSize: '0.75rem', fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase' }}
        >
          Pages
        </Typography>
      </Box>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={layout.pages.map((p) => p.id)}
          strategy={verticalListSortingStrategy}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }} data-testid="page-thumbnail-list">
            {layout.pages.map((page, index) => (
              <SortableThumbnail
                key={page.id}
                page={page}
                index={index}
                isSelected={page.id === selectedPageId}
                onClick={() => handleThumbnailClick(page.id)}
              />
            ))}
          </Box>
        </SortableContext>
      </DndContext>

      <Button
        variant="text"
        startIcon={<AddOutlined />}
        sx={{ mt: 1 }}
        onClick={handleAddPage}
      >
        Add Page
      </Button>
    </Box>
  );
}
