"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import InputAdornment from "@mui/material/InputAdornment";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import InboxIcon from "@mui/icons-material/Inbox";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import MarkEmailReadOutlinedIcon from "@mui/icons-material/MarkEmailReadOutlined";
import MarkEmailUnreadOutlinedIcon from "@mui/icons-material/MarkEmailUnreadOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import ReplyIcon from "@mui/icons-material/Reply";
import SearchIcon from "@mui/icons-material/Search";
import SendIcon from "@mui/icons-material/Send";
import {
  deleteMessage,
  getMessage,
  listMessages,
  replyToMessage,
  type MailMessage,
  type MailMessageDetail,
} from "@/lib/api/mail";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";
  const diffDays = Math.floor((now.getTime() - date.getTime()) / 86_400_000);
  if (diffDays < 7) return date.toLocaleDateString("en-GB", { weekday: "short" });
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function senderInitials(msg: MailMessage): string {
  if (msg.from_name) {
    const parts = msg.from_name.trim().split(/\s+/);
    return parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : parts[0].slice(0, 2).toUpperCase();
  }
  return msg.from_address.slice(0, 2).toUpperCase();
}

function senderDisplayName(msg: MailMessage): string {
  return msg.from_name || msg.from_address;
}

function senderFull(msg: MailMessage): string {
  return msg.from_name ? `${msg.from_name} <${msg.from_address}>` : msg.from_address;
}

const AVATAR_COLORS = [
  "#0078d4", "#107c10", "#d13438", "#5c2d91", "#ca5010",
  "#00b294", "#881798", "#004e8c", "#038387", "#8764b8",
];

function avatarColor(addr: string): string {
  let hash = 0;
  for (let i = 0; i < addr.length; i++) hash = addr.charCodeAt(i) + ((hash << 5) - hash);
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

type Folder = "inbox" | "bounces";

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function MailPage() {
  const [folder, setFolder] = useState<Folder>("inbox");
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MailMessageDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [replyOpen, setReplyOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);
  const [search, setSearch] = useState("");
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const msgs = await listMessages(0, 100);
      setMessages(msgs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load messages.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const inboxMessages = useMemo(() => messages.filter((m) => !m.is_bounce), [messages]);
  const bounceMessages = useMemo(() => messages.filter((m) => m.is_bounce), [messages]);
  const inboxUnread = useMemo(() => inboxMessages.filter((m) => !m.is_read).length, [inboxMessages]);
  const bounceUnread = useMemo(() => bounceMessages.filter((m) => !m.is_read).length, [bounceMessages]);

  const baseVisible = folder === "bounces" ? bounceMessages : inboxMessages;
  const visible = useMemo(() => {
    if (!search.trim()) return baseVisible;
    const q = search.toLowerCase();
    return baseVisible.filter(
      (m) =>
        m.subject.toLowerCase().includes(q) ||
        (m.from_name || "").toLowerCase().includes(q) ||
        m.from_address.toLowerCase().includes(q) ||
        m.preview.toLowerCase().includes(q),
    );
  }, [baseVisible, search]);

  const handleSelect = async (msg: MailMessage) => {
    if (selected?.id === msg.id) return;
    setLoadingDetail(true);
    setSelected(null);
    setReplyText("");
    setReplyOpen(false);
    setSendSuccess(false);
    try {
      const detail = await getMessage(msg.id);
      setSelected(detail);
      setMessages((prev) => prev.map((m) => (m.id === msg.id ? { ...m, is_read: true } : m)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this message.");
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleToggleRead = (msg: MailMessage | MailMessageDetail) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === msg.id ? { ...m, is_read: !m.is_read } : m)),
    );
    if (selected?.id === msg.id) {
      setSelected((prev) => (prev ? { ...prev, is_read: !prev.is_read } : null));
    }
  };

  const handleReply = async () => {
    if (!selected || !replyText.trim()) return;
    setSending(true);
    setSendSuccess(false);
    try {
      await replyToMessage(selected.id, replyText.trim());
      setReplyText("");
      setSendSuccess(true);
      setReplyOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send reply.");
    } finally {
      setSending(false);
    }
  };

  const handleDelete = async (msg: MailMessage | MailMessageDetail, e?: React.MouseEvent) => {
    e?.stopPropagation();
    try {
      await deleteMessage(msg.id);
      setMessages((prev) => prev.filter((m) => m.id !== msg.id));
      if (selected?.id === msg.id) {
        setSelected(null);
        setReplyOpen(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete this message.");
    }
  };

  const handleFolderSwitch = (f: Folder) => {
    setFolder(f);
    setSelected(null);
    setReplyOpen(false);
    setSearch("");
  };

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe || !selected?.body_html) return;
    const doc = iframe.contentDocument || iframe.contentWindow?.document;
    if (!doc) return;
    doc.open();
    doc.write(selected.body_html);
    doc.close();
  }, [selected?.body_html]);

  return (
    <Box sx={{ display: "flex", height: "100vh", bgcolor: "background.default", overflow: "hidden" }}>

      {/* ===== FOLDER SIDEBAR ===== */}
      <Box
        sx={{
          width: 220,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          bgcolor: "background.paper",
          borderRight: "1px solid",
          borderColor: "divider",
          pt: 2,
        }}
      >
        <Box sx={{ px: 2, mb: 2, display: "flex", alignItems: "center", gap: 1 }}>
          <MailOutlineIcon color="primary" sx={{ fontSize: 20 }} />
          <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.85rem" }}>
            Support Mail
          </Typography>
        </Box>

        <List dense disablePadding>
          <ListItemButton
            selected={folder === "inbox"}
            onClick={() => handleFolderSwitch("inbox")}
            sx={{ mx: 1, mb: 0.5, borderRadius: 1, px: 1.5 }}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              <InboxIcon sx={{ fontSize: 18, color: folder === "inbox" ? "primary.main" : "text.secondary" }} />
            </ListItemIcon>
            <ListItemText
              primary="Inbox"
              primaryTypographyProps={{ fontSize: "0.85rem", fontWeight: folder === "inbox" ? 600 : 400 }}
            />
            {inboxUnread > 0 && (
              <Typography
                sx={{
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color: "primary.contrastText",
                  bgcolor: "primary.main",
                  px: 0.8,
                  py: 0.15,
                  borderRadius: 1,
                  lineHeight: 1.6,
                  minWidth: 18,
                  textAlign: "center",
                }}
              >
                {inboxUnread}
              </Typography>
            )}
          </ListItemButton>

          <ListItemButton
            selected={folder === "bounces"}
            onClick={() => handleFolderSwitch("bounces")}
            sx={{ mx: 1, mb: 0.5, borderRadius: 1, px: 1.5 }}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              <ErrorOutlineIcon sx={{ fontSize: 18, color: folder === "bounces" ? "error.main" : "text.secondary" }} />
            </ListItemIcon>
            <ListItemText
              primary="Bounces"
              primaryTypographyProps={{ fontSize: "0.85rem", fontWeight: folder === "bounces" ? 600 : 400 }}
            />
            {bounceUnread > 0 && (
              <Typography
                sx={{
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color: "error.contrastText",
                  bgcolor: "error.main",
                  px: 0.8,
                  py: 0.15,
                  borderRadius: 1,
                  lineHeight: 1.6,
                  minWidth: 18,
                  textAlign: "center",
                }}
              >
                {bounceUnread}
              </Typography>
            )}
          </ListItemButton>
        </List>

        <Box sx={{ flex: 1 }} />

        <Box sx={{ px: 2, pb: 2, borderTop: "1px solid", borderColor: "divider", pt: 1.5 }}>
          <Tooltip title="Refresh messages">
            <span>
              <IconButton size="small" onClick={load} disabled={loading} sx={{ color: "text.secondary" }}>
                {loading ? <CircularProgress size={16} /> : <RefreshIcon fontSize="small" />}
              </IconButton>
            </span>
          </Tooltip>
        </Box>
      </Box>

      {/* ===== MESSAGE LIST ===== */}
      <Box
        sx={{
          width: 360,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          bgcolor: "background.paper",
          borderRight: "1px solid",
          borderColor: "divider",
        }}
      >
        {/* List header + search */}
        <Box sx={{ px: 2, pt: 2, pb: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 700, fontSize: "0.9rem" }}>
              {folder === "bounces" ? "Bounces" : "Inbox"}
              {!loading && (
                <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1 }}>
                  {visible.length}
                </Typography>
              )}
            </Typography>
          </Box>
          <TextField
            size="small"
            fullWidth
            placeholder={`Search ${folder === "bounces" ? "bounces" : "inbox"}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            slotProps={{
              input: {
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ fontSize: 16, color: "text.disabled" }} />
                  </InputAdornment>
                ),
                endAdornment: search ? (
                  <InputAdornment position="end">
                    <IconButton size="small" onClick={() => setSearch("")} edge="end">
                      <CloseIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  </InputAdornment>
                ) : null,
              },
            }}
            sx={{ "& .MuiOutlinedInput-root": { fontSize: "0.82rem" } }}
          />
        </Box>

        {error && (
          <Alert severity="error" sx={{ mx: 2, mt: 1.5 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Message rows */}
        <Box sx={{ flex: 1, overflowY: "auto" }}>
          {loading && (
            <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
              <CircularProgress size={28} />
            </Box>
          )}

          {!loading && visible.length === 0 && (
            <Box sx={{ textAlign: "center", py: 8, px: 3 }}>
              {search ? (
                <>
                  <SearchIcon sx={{ fontSize: 40, color: "text.disabled", mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">
                    No results for &ldquo;{search}&rdquo;
                  </Typography>
                </>
              ) : (
                <>
                  <InboxIcon sx={{ fontSize: 40, color: "text.disabled", mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">
                    {folder === "bounces" ? "No bounced emails" : "Your inbox is empty"}
                  </Typography>
                </>
              )}
            </Box>
          )}

          {visible.map((msg) => {
            const isSelected = selected?.id === msg.id;
            const color = avatarColor(msg.from_address);
            return (
              <Box
                key={msg.id}
                onClick={() => handleSelect(msg)}
                sx={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 1.5,
                  px: 2,
                  py: 1.5,
                  cursor: "pointer",
                  borderBottom: "1px solid",
                  borderColor: "divider",
                  bgcolor: isSelected ? "action.selected" : "transparent",
                  borderLeft: "3px solid",
                  borderLeftColor: isSelected ? "primary.main" : "transparent",
                  transition: "background-color 0.1s, border-left-color 0.1s",
                  "&:hover": {
                    bgcolor: isSelected ? "action.selected" : "action.hover",
                    "& .msg-row-actions": { opacity: 1 },
                  },
                  position: "relative",
                }}
              >
                {/* Unread dot */}
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    bgcolor: msg.is_read ? "transparent" : "primary.main",
                    flexShrink: 0,
                    mt: 1.25,
                  }}
                />

                {/* Avatar */}
                <Avatar
                  sx={{
                    width: 36,
                    height: 36,
                    bgcolor: color,
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  {senderInitials(msg)}
                </Avatar>

                {/* Content */}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", mb: 0.25 }}>
                    <Typography
                      sx={{
                        fontSize: "0.82rem",
                        fontWeight: msg.is_read ? 400 : 700,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        flex: 1,
                        mr: 1,
                      }}
                    >
                      {senderDisplayName(msg)}
                    </Typography>
                    <Typography sx={{ fontSize: "0.68rem", color: "text.secondary", flexShrink: 0, whiteSpace: "nowrap" }}>
                      {formatTimestamp(msg.received_at)}
                    </Typography>
                  </Box>

                  <Typography
                    sx={{
                      fontSize: "0.78rem",
                      fontWeight: msg.is_read ? 400 : 600,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      color: "text.primary",
                      mb: 0.25,
                    }}
                  >
                    {msg.subject}
                  </Typography>

                  <Typography
                    sx={{
                      fontSize: "0.73rem",
                      color: "text.secondary",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      display: "block",
                    }}
                  >
                    {msg.preview}
                  </Typography>

                  {msg.is_bounce && (
                    <Chip
                      label="Bounced"
                      color="error"
                      size="small"
                      sx={{ height: 16, fontSize: "0.62rem", mt: 0.5, "& .MuiChip-label": { px: 0.6 } }}
                    />
                  )}
                </Box>

                {/* Hover action buttons */}
                <Box
                  className="msg-row-actions"
                  sx={{
                    position: "absolute",
                    right: 6,
                    top: 6,
                    display: "flex",
                    gap: 0.25,
                    opacity: 0,
                    transition: "opacity 0.15s",
                    bgcolor: "background.paper",
                    borderRadius: 1,
                    boxShadow: 1,
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <Tooltip title={msg.is_read ? "Mark as unread" : "Mark as read"}>
                    <IconButton size="small" onClick={() => handleToggleRead(msg)} sx={{ p: 0.5 }}>
                      {msg.is_read
                        ? <MarkEmailUnreadOutlinedIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                        : <MarkEmailReadOutlinedIcon sx={{ fontSize: 14, color: "text.secondary" }} />}
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <IconButton size="small" onClick={(e) => handleDelete(msg, e)} sx={{ p: 0.5 }}>
                      <DeleteOutlineIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* ===== READING PANE ===== */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, bgcolor: "background.default" }}>
        {loadingDetail && (
          <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", flex: 1 }}>
            <CircularProgress />
          </Box>
        )}

        {!loadingDetail && !selected && (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              flex: 1,
              gap: 1.5,
              color: "text.disabled",
            }}
          >
            <MailOutlineIcon sx={{ fontSize: 64, opacity: 0.3 }} />
            <Typography variant="body2" color="text.secondary">
              Select a message to read
            </Typography>
          </Box>
        )}

        {!loadingDetail && selected && (
          <>
            {/* Reading pane action toolbar */}
            <Box
              sx={{
                px: 2,
                py: 0.75,
                borderBottom: "1px solid",
                borderColor: "divider",
                bgcolor: "background.paper",
                display: "flex",
                alignItems: "center",
                gap: 0.5,
              }}
            >
              <Tooltip title={selected.is_bounce ? "Cannot reply to a bounce" : "Reply"}>
                <span>
                  <Button
                    size="small"
                    variant={replyOpen ? "contained" : "outlined"}
                    startIcon={<ReplyIcon sx={{ fontSize: 16 }} />}
                    onClick={() => setReplyOpen((o) => !o)}
                    disabled={selected.is_bounce}
                    sx={{ fontSize: "0.78rem", textTransform: "none", px: 1.5 }}
                  >
                    Reply
                  </Button>
                </span>
              </Tooltip>

              <Divider orientation="vertical" flexItem sx={{ mx: 0.5 }} />

              <Tooltip title={selected.is_read ? "Mark as unread" : "Mark as read"}>
                <IconButton size="small" onClick={() => handleToggleRead(selected)}>
                  {selected.is_read
                    ? <MarkEmailUnreadOutlinedIcon sx={{ fontSize: 18 }} />
                    : <MarkEmailReadOutlinedIcon sx={{ fontSize: 18 }} />}
                </IconButton>
              </Tooltip>

              <Tooltip title="Delete">
                <IconButton size="small" onClick={() => handleDelete(selected)}>
                  <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                </IconButton>
              </Tooltip>
            </Box>

            {/* Message header */}
            <Box
              sx={{
                px: 3,
                py: 2.5,
                borderBottom: "1px solid",
                borderColor: "divider",
                bgcolor: "background.paper",
                display: "flex",
                gap: 2,
                alignItems: "flex-start",
              }}
            >
              <Avatar
                sx={{
                  width: 44,
                  height: 44,
                  bgcolor: avatarColor(selected.from_address),
                  fontSize: "0.9rem",
                  fontWeight: 700,
                  flexShrink: 0,
                  mt: 0.5,
                }}
              >
                {senderInitials(selected)}
              </Avatar>

              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1, mb: 0.5 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                      {selected.subject}
                    </Typography>
                    {selected.is_bounce && (
                      <Chip label="Bounced" color="error" size="small" sx={{ height: 18, fontSize: "0.68rem" }} />
                    )}
                  </Box>
                  <Typography sx={{ fontSize: "0.78rem", color: "text.secondary", flexShrink: 0, whiteSpace: "nowrap" }}>
                    {new Date(selected.received_at).toLocaleString("en-GB", { dateStyle: "long", timeStyle: "short" })}
                  </Typography>
                </Box>
                <Typography sx={{ fontSize: "0.82rem", color: "text.secondary" }}>
                  <strong>From:</strong> {senderFull(selected)}
                </Typography>
              </Box>
            </Box>

            {/* Inline alerts */}
            {sendSuccess && (
              <Alert severity="success" sx={{ mx: 3, mt: 1.5, fontSize: "0.82rem" }} onClose={() => setSendSuccess(false)}>
                Reply sent successfully.
              </Alert>
            )}
            {selected.is_bounce && (
              <Alert severity="warning" sx={{ mx: 3, mt: 1.5, fontSize: "0.82rem" }}>
                This is a bounce notification. The original email did not reach the recipient.
                Please verify the address and re-send the invite if needed.
              </Alert>
            )}

            {/* Email body */}
            <Box sx={{ flex: 1, overflow: "hidden", bgcolor: "#fff" }}>
              <iframe
                ref={iframeRef}
                sandbox="allow-same-origin"
                style={{ width: "100%", height: "100%", border: "none" }}
                title="Email body"
              />
            </Box>

            {/* Inline reply composer */}
            <Collapse in={replyOpen}>
              <Box
                sx={{
                  px: 3,
                  py: 2,
                  bgcolor: "background.paper",
                  borderTop: "1px solid",
                  borderColor: "divider",
                }}
              >
                <Box
                  sx={{
                    border: "1px solid",
                    borderColor: "divider",
                    borderRadius: 1,
                    overflow: "hidden",
                  }}
                >
                  {/* Composer header */}
                  <Box
                    sx={{
                      px: 2,
                      py: 1,
                      bgcolor: "action.hover",
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                    }}
                  >
                    <ReplyIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                    <Typography sx={{ fontSize: "0.78rem", color: "text.secondary", flex: 1 }}>
                      Reply to: {senderFull(selected)}
                    </Typography>
                    <IconButton
                      size="small"
                      onClick={() => { setReplyOpen(false); setReplyText(""); }}
                      sx={{ p: 0.25 }}
                    >
                      <CloseIcon sx={{ fontSize: 14 }} />
                    </IconButton>
                  </Box>

                  {/* Composer body */}
                  <TextField
                    multiline
                    rows={4}
                    fullWidth
                    placeholder="Write your reply…"
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    variant="standard"
                    slotProps={{
                      input: {
                        disableUnderline: true,
                        sx: { px: 2, py: 1.5, fontSize: "0.85rem" },
                      },
                    }}
                  />

                  {/* Composer footer */}
                  <Box
                    sx={{
                      px: 2,
                      py: 1,
                      borderTop: "1px solid",
                      borderColor: "divider",
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                    }}
                  >
                    <Button
                      variant="contained"
                      size="small"
                      startIcon={
                        sending
                          ? <CircularProgress size={12} color="inherit" />
                          : <SendIcon sx={{ fontSize: 14 }} />
                      }
                      onClick={handleReply}
                      disabled={sending || !replyText.trim()}
                      sx={{ textTransform: "none", fontSize: "0.82rem" }}
                    >
                      {sending ? "Sending…" : "Send"}
                    </Button>
                    <Button
                      variant="text"
                      size="small"
                      onClick={() => { setReplyOpen(false); setReplyText(""); }}
                      sx={{ textTransform: "none", fontSize: "0.82rem", color: "text.secondary" }}
                    >
                      Discard
                    </Button>
                  </Box>
                </Box>
              </Box>
            </Collapse>
          </>
        )}
      </Box>
    </Box>
  );
}
