"use client";

import Box from "@mui/material/Box";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Typography from "@mui/material/Typography";
import LabelIcon from "@mui/icons-material/Label";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import SpaceBarIcon from "@mui/icons-material/SpaceBar";
import AddCircleIcon from "@mui/icons-material/AddCircle";
import DeleteIcon from "@mui/icons-material/Delete";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import type { Correction } from "@/lib/types";

interface Props {
  corrections: Correction[];
}

const TYPE_ICONS: Record<string, React.ReactNode> = {
  context: <LabelIcon fontSize="small" color="primary" />,
  reassign: <SwapHorizIcon fontSize="small" color="info" />,
  span: <SpaceBarIcon fontSize="small" color="action" />,
  add: <AddCircleIcon fontSize="small" color="success" />,
  remove: <DeleteIcon fontSize="small" color="error" />,
};

export default function CorrectionsLog({ corrections }: Props) {
  if (corrections.length === 0) {
    return (
      <Typography variant="body2" sx={{ p: 2, color: "text.disabled" }}>
        No corrections yet. Click an entity to edit.
      </Typography>
    );
  }

  return (
    <Box sx={{ maxHeight: 280, overflowY: "auto" }}>
      <List disablePadding>
        {corrections.map((c, i) => (
          <ListItem
            key={i}
            sx={{
              borderBottom: 1,
              borderColor: "grey.100",
              animation: "slideIn 0.2s ease",
              py: 1,
              px: 2,
            }}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              {TYPE_ICONS[c.type] || <FiberManualRecordIcon sx={{ fontSize: 8 }} />}
            </ListItemIcon>
            <ListItemText
              primary={c.text}
              primaryTypographyProps={{ variant: "body2", fontWeight: 600 }}
              secondary={c.detail}
              secondaryTypographyProps={{ variant: "caption" }}
            />
          </ListItem>
        ))}
      </List>
    </Box>
  );
}
