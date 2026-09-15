/**
 * Split completed guideline matches out of Assessment markdown.
 *
 * Atlas trace:
 *   DI: DI-B3B44F09
 *   DI: DI-613A48DA
 */

const ALREADY_DONE_HEADING = /^### Already done(?: \((\d+)\))?\s*$/m;

export interface AlreadyDoneSplit {
  openBody: string;
  doneBody: string;
  count: number;
}

export function splitAlreadyDoneAssessment(body: string): AlreadyDoneSplit {
  const text = body ?? "";
  const match = text.match(ALREADY_DONE_HEADING);
  if (!match || match.index == null) {
    return { openBody: text, doneBody: "", count: 0 };
  }
  const openBody = text.slice(0, match.index).trim();
  const doneBody = text.slice(match.index + match[0].length).trim();
  const counted = Number.parseInt(match[1] ?? "", 10);
  const count = Number.isFinite(counted)
    ? counted
    : (doneBody.match(/^- \*\*/gm) ?? []).length;
  return { openBody, doneBody, count };
}
