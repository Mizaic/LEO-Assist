"use client";

import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Paper from "@mui/material/Paper";
import Slider from "@mui/material/Slider";
import Switch from "@mui/material/Switch";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import LogoutIcon from "@mui/icons-material/Logout";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import {
  deleteAllSessions,
  deleteSession,
  getAuthConfig,
  listSessions,
  patchAuthConfig,
  type AuthConfig,
  type Session,
} from "@/lib/api/admin";
import ConfirmDialog from "@/components/ConfirmDialog";

// ------------------------------------------------------------------
// Helpers
// ------------------------------------------------------------------

function ttlLabel(hours: number): string {
  if (hours < 24) return `${hours} hour${hours !== 1 ? "s" : ""}`;
  const days = Math.round(hours / 24);
  return `${days} day${days !== 1 ? "s" : ""}`;
}

function ttlRemaining(ttlSeconds: number): string {
  const mins = Math.round(ttlSeconds / 60);
  if (mins < 60) return `${mins} min${mins !== 1 ? "s" : ""} left`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} hr${hrs !== 1 ? "s" : ""} left`;
  const days = Math.round(hrs / 24);
  return `${days} day${days !== 1 ? "s" : ""} left`;
}

// ------------------------------------------------------------------
// Component
// ------------------------------------------------------------------

export default function AuthConfig() {
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [sessionTtl, setSessionTtl] = useState(168);
  const [idleTimeout, setIdleTimeout] = useState(30);
  const [cookieSecure, setCookieSecure] = useState(false);
  const [requireMfa, setRequireMfa] = useState(false);

  const [logoutAllConfirm, setLogoutAllConfirm] = useState(false);

  // Group sessions by email for a cleaner display
  const sessionsByEmail = sessions.reduce<Record<string, Session[]>>((acc, s) => {
    const key = s.email || "unknown";
    acc[key] = acc[key] || [];
    acc[key].push(s);
    return acc;
  }, {});
  const emailList = Object.keys(sessionsByEmail).sort();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [c, s] = await Promise.all([getAuthConfig(), listSessions()]);
      setConfig(c);
      setSessionTtl(c.session_ttl_hours);
      setIdleTimeout(c.idle_timeout_minutes);
      setCookieSecure(c.cookie_secure);
      setRequireMfa(c.require_mfa);
      setSessions(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await patchAuthConfig({
        session_ttl_hours: sessionTtl,
        idle_timeout_minutes: idleTimeout,
        cookie_secure: cookieSecure,
        require_mfa: requireMfa,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign this person out.");
    }
  };

  const handleLogoutAll = async () => {
    try {
      await deleteAllSessions();
      setLogoutAllConfirm(false);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign everyone out.");
    }
  };

  const isDirty =
    config &&
    (sessionTtl !== config.session_ttl_hours ||
      idleTimeout !== config.idle_timeout_minutes ||
      cookieSecure !== config.cookie_secure ||
      requireMfa !== config.require_mfa);

  return (
    <Box>
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {saved && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Settings saved.
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress aria-label="Loading" />
        </Box>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 4 }}>

          {/* ---- LOGIN SESSION SETTINGS ---- */}
          <Paper variant="outlined" sx={{ p: 3, borderRadius: 2 }}>
            <Alert severity="info" icon={<InfoOutlinedIcon />} sx={{ mb: 2.5, fontSize: "0.82rem" }}>
              <strong>Session length and idle timeout</strong> apply the next time someone logs in.
              People who are already logged in keep their current session length.
              Sign everyone out (below) if you need the new settings to take effect now.
            </Alert>

            <Typography variant="subtitle1" sx={{ fontWeight: 700, mb: 0.5 }}>
              How long do people stay logged in?
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              After this time, people will be asked to log in again.
            </Typography>

            <Box sx={{ maxWidth: 440 }}>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Session length</Typography>
                <Chip
                  label={ttlLabel(sessionTtl)}
                  color="primary"
                  size="small"
                  variant="outlined"
                />
              </Box>
              <Slider
                value={sessionTtl}
                onChange={(_, v) => setSessionTtl(v as number)}
                min={1}
                max={168}
                step={1}
                valueLabelDisplay="auto"
                valueLabelFormat={ttlLabel}
                marks={[
                  { value: 1, label: "1h" },
                  { value: 24, label: "1d" },
                  { value: 72, label: "3d" },
                  { value: 168, label: "7d" },
                ]}
                sx={{ mb: 0.5 }}
              />
              <Typography variant="caption" color="text.secondary">
                People who are inactive for {ttlLabel(sessionTtl)} will need to log in again.
              </Typography>
            </Box>

            <Divider sx={{ my: 3 }} />

            <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
              Warn before logging out (idle timeout)
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              If someone does not move their mouse or type for this long, show them a warning. Set to 0 to turn this off.
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <TextField
                type="number"
                value={idleTimeout}
                onChange={(e) => setIdleTimeout(Math.max(0, parseInt(e.target.value, 10) || 0))}
                size="small"
                sx={{ width: 100 }}
                inputProps={{ min: 0, max: 480 }}
              />
              <Typography variant="body2" color="text.secondary">minutes</Typography>
              {idleTimeout === 0 && (
                <Chip label="Off" size="small" color="default" variant="outlined" />
              )}
            </Box>

            <Divider sx={{ my: 3 }} />

            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              <Box>
                <FormControlLabel
                  control={
                    <Switch
                      checked={cookieSecure}
                      onChange={(e) => setCookieSecure(e.target.checked)}
                    />
                  }
                  label={
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        Secure cookies (HTTPS only)
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Only use this if your site uses HTTPS. Turning it on for a plain HTTP site will break logins.
                      </Typography>
                    </Box>
                  }
                />
                {cookieSecure !== config?.cookie_secure && (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5, ml: 7 }}>
                    <WarningAmberIcon fontSize="small" color="warning" />
                    <Typography variant="caption" color="warning.main">
                      Changing this will sign everyone out. Restart the service after saving.
                    </Typography>
                  </Box>
                )}
              </Box>

              <FormControlLabel
                control={
                  <Switch
                    checked={requireMfa}
                    onChange={(e) => setRequireMfa(e.target.checked)}
                  />
                }
                label={
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      Require two-step login (MFA)
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Extra check when people log in. Recommended for NHS data.
                    </Typography>
                  </Box>
                }
              />
            </Box>

            <Box sx={{ mt: 3 }}>
              <Button
                variant="contained"
                onClick={handleSave}
                disabled={saving || !isDirty}
              >
                {saving ? "Saving..." : isDirty ? "Save changes" : "No changes"}
              </Button>
            </Box>
          </Paper>

          {/* ---- ACTIVE SESSIONS ---- */}
          <Paper variant="outlined" sx={{ p: 3, borderRadius: 2 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 0.5 }}>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                  Who is logged in right now?
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {sessions.length} active session{sessions.length !== 1 ? "s" : ""} across {emailList.length} person{emailList.length !== 1 ? "s" : ""}.
                </Typography>
              </Box>
              <Tooltip title="Signs everyone out immediately. They will need to log back in.">
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  startIcon={<LogoutIcon />}
                  onClick={() => setLogoutAllConfirm(true)}
                  disabled={sessions.length === 0}
                >
                  Sign everyone out
                </Button>
              </Tooltip>
            </Box>

            {sessions.length === 0 ? (
              <Box sx={{ textAlign: "center", py: 4 }}>
                <Typography variant="body2" color="text.secondary">
                  Nobody is logged in right now.
                </Typography>
              </Box>
            ) : (
              <Table size="small" sx={{ mt: 2 }}>
                <TableHead>
                  <TableRow sx={{ "& th": { fontWeight: 700, fontSize: "0.78rem", color: "text.secondary" } }}>
                    <TableCell>Person</TableCell>
                    <TableCell align="right">Sessions</TableCell>
                    <TableCell>Expires</TableCell>
                    <TableCell></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {emailList.map((email) => {
                    const userSessions = sessionsByEmail[email];
                    const minTtl = Math.min(...userSessions.map((s) => s.ttl_seconds));
                    const maxTtl = Math.max(...userSessions.map((s) => s.ttl_seconds));
                    return (
                      <TableRow key={email} hover sx={{ "&:last-child td": { border: 0 } }}>
                        <TableCell sx={{ fontWeight: 500, fontSize: "0.85rem" }}>{email}</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${userSessions.length} device${userSessions.length > 1 ? "s" : ""}`}
                            size="small"
                            color={userSessions.length > 5 ? "warning" : "default"}
                            variant="outlined"
                            sx={{ fontSize: "0.7rem" }}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary">
                            {ttlRemaining(minTtl)}
                            {minTtl !== maxTtl && ` – ${ttlRemaining(maxTtl)}`}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                            color="error"
                            startIcon={<LogoutIcon />}
                            onClick={async () => {
                              try {
                                await Promise.all(
                                  userSessions.map((s) => deleteSession(s.session_id))
                                );
                                load();
                              } catch {
                                setError("Could not sign this person out.");
                              }
                            }}
                            sx={{ fontSize: "0.72rem" }}
                          >
                            Sign out
                          </Button>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </Paper>
        </Box>
      )}

      {logoutAllConfirm && (
        <ConfirmDialog
          title="Sign everyone out"
          body="This will sign out every person who is currently logged in, on all their devices. They can log back in straight away."
          confirmLabel="Yes, sign everyone out"
          variant="danger"
          onConfirm={handleLogoutAll}
          onCancel={() => setLogoutAllConfirm(false)}
        />
      )}
    </Box>
  );
}
