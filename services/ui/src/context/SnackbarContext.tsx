/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-A2553F87
 *   DI: DI-425CA252
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-A2553F87")
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";

export type SnackbarSeverity = "success" | "info" | "warning" | "error";

export interface SnackbarOptions {
  action?: {
    label: string;
    onClick: () => void;
  };
  severity?: SnackbarSeverity;
}

interface SnackbarContextValue {
  showSnackbar: (
    message: string,
    options?: SnackbarOptions
  ) => void;
}

const SnackbarContext = createContext<SnackbarContextValue | null>(null);

const AUTO_HIDE_DURATION = 5000;

export function SnackbarProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [severity, setSeverity] = useState<SnackbarSeverity>("info");
  const [action, setAction] = useState<SnackbarOptions["action"]>(undefined);

  const showSnackbar = useCallback(
    (msg: string, options?: SnackbarOptions) => {
      setMessage(msg);
      setSeverity(options?.severity ?? "info");
      setAction(options?.action);
      setOpen(true);
    },
    []
  );

  const handleClose = useCallback(
    (_event?: React.SyntheticEvent | Event, reason?: string) => {
      if (reason === "clickaway") return;
      setOpen(false);
    },
    []
  );

  const handleActionClick = useCallback(() => {
    action?.onClick();
    setOpen(false);
  }, [action]);

  const value: SnackbarContextValue = { showSnackbar };

  return (
    <SnackbarContext.Provider value={value}>
      {children}
      <Snackbar
        open={open}
        autoHideDuration={AUTO_HIDE_DURATION}
        onClose={handleClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert
          onClose={handleClose}
          severity={severity}
          variant="filled"
          action={
            action ? (
              <Button
                color="inherit"
                size="small"
                onClick={handleActionClick}
                sx={{ fontWeight: 600, textTransform: "none" }}
              >
                {action.label}
              </Button>
            ) : undefined
          }
          sx={{ width: "100%" }}
        >
          {message}
        </Alert>
      </Snackbar>
    </SnackbarContext.Provider>
  );
}

export function useSnackbar(): SnackbarContextValue {
  const ctx = useContext(SnackbarContext);
  if (!ctx) {
    throw new Error("useSnackbar must be used within SnackbarProvider");
  }
  return ctx;
}
