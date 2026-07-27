/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DI: DI-42246DA7
 *   DO: DO-F8C56339
 */
"use client";

/**
 * Replaces the old single generic "One of the groups is empty" banner
 * with an issue-count headline plus one "Take me there" button per
 * problem, so the reviewer is never left guessing which one of several
 * problems a vague message refers to, or where it lives in the tree.
 *
 * Every issue lists its own plain-English message (reading age 9-11)
 * next to its own jump button -- there is deliberately no "next
 * problem" carousel: with the small number of issues a rule normally
 * has, showing them all at once is both simpler to implement and
 * clearer to read than making the reviewer click through a cycle.
 */
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { ValidationIssue } from "./treeOps";

export interface ValidationIssueBannerProps {
  issues: ValidationIssue[];
  /** Omitted (or an issue with no `nodeId`) means there is nothing on
   *  screen to jump to -- the message still shows, just without a
   *  button. */
  onJumpToIssue?: (nodeId: string) => void;
}

function countHeadline(count: number): string {
  return count === 1 ? "We found 1 problem." : `We found ${count} problems.`;
}

export default function ValidationIssueBanner({
  issues,
  onJumpToIssue,
}: ValidationIssueBannerProps) {
  if (issues.length === 0) return null;
  return (
    <Alert severity="warning" sx={{ py: 0.75, mb: 2 }} role="status">
      <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>
        {countHeadline(issues.length)}
      </Typography>
      <Stack spacing={0.5}>
        {issues.map((issue, index) => (
          <Stack
            key={issue.nodeId ?? index}
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{ flexWrap: "wrap", rowGap: 0.5 }}
          >
            <Typography variant="body2" sx={{ flexGrow: 1, minWidth: 0 }}>
              {issue.message}
            </Typography>
            {issue.nodeId && onJumpToIssue && (
              <Button
                size="small"
                variant="outlined"
                color="warning"
                onClick={() => onJumpToIssue(issue.nodeId!)}
                sx={{ whiteSpace: "nowrap" }}
              >
                Take me there
              </Button>
            )}
          </Stack>
        ))}
      </Stack>
    </Alert>
  );
}
