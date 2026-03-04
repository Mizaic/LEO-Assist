"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ReplyIcon from "@mui/icons-material/Reply";
import RefreshIcon from "@mui/icons-material/Refresh";
import MailOutlineIcon from "@mui/icons-material/MailOutline";
import DraftsOutlinedIcon from "@mui/icons-material/DraftsOutlined";
import {
  listMessages,
  getMessage,
  replyToMessage,
  deleteMessage,
  type MailMessage,
  type MailMessageDetail,
} from "@/lib/api/mail";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function senderLabel(msg: MailMessage): string {
  return msg.from_name
    ? `${msg.from_name} <${msg.from_address}>`
    : msg.from_address;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function MailPage() {
  const [tab, setTab] = useState<"all" | "bounces">("all");
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MailMessageDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);
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

  const visible = tab === "bounces" ? messages.filter((m) => m.is_bounce) : messages;

  const handleSelect = async (msg: MailMessage) => {
    setLoadingDetail(true);
    setSelected(null);
    setReplyText("");
    setSendSuccess(false);
    try {
      const detail = await getMessage(msg.id);
      setSelected(detail);
      setMessages((prev) =>
        prev.map((m) => (m.id === msg.id ? { ...m, is_read: true } : m))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this message.");
    } finally {
      setLoadingDetail(false);
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
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send reply.");
    } finally {
      setSending(false);
    }
  };

  const handleDelete = async (msg: MailMessage) => {
    try {
      await deleteMessage(msg.id);
      setMessages((prev) => prev.filter((m) => m.id !== msg.id));
      if (selected?.id === msg.id) setSelected(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete this message.");
    }
  };

  // Write HTML into the sandboxed iframe to avoid XSS
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
    <Box sx={{ display: "flex", flexDirection: "column", height: "100vh", bgcolor: "background.default" }}>
      {/* Header */}
      <Box sx={{ px: 3, pt: 3, pb: 1.5, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
          <MailOutlineIcon color="primary" />
          <Typography variant="h6" component="h1" sx={{ fontWeight: 700 }}>
            Support Mail
          </Typography>
          <Tooltip title="Refresh">
            <IconButton aria-label="Refresh" size="small" onClick={load} disabled={loading}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Typography variant="body2" color="text.secondary">
          Messages sent to leo.support@healthcarecopilot.ai. Reply or delete from here.
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mx: 3, mt: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Box sx={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* ---- Left: message list ---- */}
        <Box
          sx={{
            width: 340,
            flexShrink: 0,
            borderRight: "1px solid",
            borderColor: "divider",
            display: "flex",
            flexDirection: "column",
            bgcolor: "background.paper",
          }}
        >
          <Tabs
            value={tab}
            onChange={(_, v) => setTab(v)}
            sx={{ borderBottom: "1px solid", borderColor: "divider", px: 1 }}
            textColor="primary"
            indicatorColor="primary"
          >
            <Tab label="All" value="all" sx={{ fontSize: "0.8rem", minWidth: 60 }} />
            <Tab
              label={
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  Bounces
                  {messages.filter((m) => m.is_bounce).length > 0 && (
                    <Chip
                      label={messages.filter((m) => m.is_bounce).length}
                      color="error"
                      size="small"
                      sx={{ height: 16, fontSize: "0.65rem", "& .MuiChip-label": { px: 0.6 } }}
                    />
                  )}
                </Box>
              }
              value="bounces"
              sx={{ fontSize: "0.8rem", minWidth: 80 }}
            />
          </Tabs>

          <Box sx={{ flex: 1, overflowY: "auto" }}>
            {loading && (
              <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
                <CircularProgress aria-label="Loading" size={28} />
              </Box>
            )}
            {!loading && visible.length === 0 && (
              <Box sx={{ textAlign: "center", py: 6, px: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  {tab === "bounces" ? "No bounced emails." : "No messages yet."}
                </Typography>
              </Box>
            )}
            {visible.map((msg) => (
              <Box
                key={msg.id}
                onClick={() => handleSelect(msg)}
                sx={{
                  px: 2,
                  py: 1.5,
                  cursor: "pointer",
                  borderBottom: "1px solid",
                  borderColor: "divider",
                  bgcolor: selected?.id === msg.id ? "action.selected" : "transparent",
                  "&:hover": { bgcolor: "action.hover" },
                }}
              >
                <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.3 }}>
                      {msg.is_read
                        ? <DraftsOutlinedIcon sx={{ fontSize: 14, color: "text.disabled", flexShrink: 0 }} />
                        : <MailOutlineIcon sx={{ fontSize: 14, color: "primary.main", flexShrink: 0 }} />}
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: msg.is_read ? 400 : 700,
                          fontSize: "0.82rem",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {msg.from_name || msg.from_address}
                      </Typography>
                    </Box>
                    <Typography
                      variant="body2"
                      sx={{
                        fontSize: "0.78rem",
                        fontWeight: msg.is_read ? 400 : 600,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        color: "text.primary",
                      }}
                    >
                      {msg.subject}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}
                    >
                      {msg.preview}
                    </Typography>
                  </Box>
                  <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 0.5, flexShrink: 0 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.68rem" }}>
                      {relativeTime(msg.received_at)}
                    </Typography>
                    {msg.is_bounce && (
                      <Chip label="Bounce" color="error" size="small" sx={{ height: 16, fontSize: "0.62rem", "& .MuiChip-label": { px: 0.6 } }} />
                    )}
                    <Tooltip title="Delete">
                      <IconButton
                        aria-label="Delete message"
                        size="small"
                        onClick={(e) => { e.stopPropagation(); handleDelete(msg); }}
                        sx={{ p: 0.25 }}
                      >
                        <DeleteOutlineIcon sx={{ fontSize: 14, color: "text.disabled" }} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </Box>
            ))}
          </Box>
        </Box>

        {/* ---- Right: message detail + reply ---- */}
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {loadingDetail && (
            <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", flex: 1 }}>
              <CircularProgress aria-label="Loading" />
            </Box>
          )}

          {!loadingDetail && !selected && (
            <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", flex: 1, color: "text.disabled" }}>
              <MailOutlineIcon sx={{ fontSize: 56, mb: 1.5, opacity: 0.3 }} />
              <Typography variant="body2" color="text.secondary">
                Select a message to read it.
              </Typography>
            </Box>
          )}

          {!loadingDetail && selected && (
            <>
              {/* Message header */}
              <Box sx={{ px: 3, py: 2, borderBottom: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
                  {selected.subject}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  From: {senderLabel(selected)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {new Date(selected.received_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}
                </Typography>
                {selected.is_bounce && (
                  <Chip label="Bounced email" color="error" size="small" sx={{ ml: 1.5 }} />
                )}
              </Box>

              {/* Message body */}
              <Box sx={{ flex: 1, overflow: "hidden", bgcolor: "#fafafa" }}>
                <iframe
                  ref={iframeRef}
                  sandbox="allow-same-origin"
                  style={{ width: "100%", height: "100%", border: "none" }}
                  title="Email body"
                />
              </Box>

              <Divider />

              {/* Reply area */}
              <Box sx={{ px: 3, py: 2, bgcolor: "background.paper" }}>
                {selected.is_bounce ? (
                  <Alert severity="warning" sx={{ fontSize: "0.82rem" }}>
                    This is a bounce. The original invite did not reach the recipient.
                    You may need to check the email address and add them again.
                  </Alert>
                ) : (
                  <>
                    {sendSuccess && (
                      <Alert severity="success" sx={{ mb: 1.5, fontSize: "0.82rem" }}>
                        Reply sent.
                      </Alert>
                    )}
                    <TextField
                      multiline
                      rows={3}
                      fullWidth
                      placeholder="Write a reply..."
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      size="small"
                      sx={{ mb: 1.5 }}
                    />
                    <Button
                      variant="contained"
                      startIcon={<ReplyIcon />}
                      onClick={handleReply}
                      disabled={sending || !replyText.trim()}
                    >
                      {sending ? "Sending..." : "Send reply"}
                    </Button>
                  </>
                )}
              </Box>
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
}
