/** Shared clinical document preview styling for inline HTML viewers.
 *
 * Atlas trace:
 *   DO: DO-5F9A50D8
 *   DI: DI-1D584D40
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5F9A50D8")
 */
export const CLINICAL_PREVIEW_CSS = `
  :root {
    color-scheme: light;
  }
  body {
    margin: 0;
    padding: 32px 40px 48px;
    font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 15px;
    line-height: 1.65;
    color: #1e293b;
    background: #ffffff;
  }
  h1, h2, h3, h4 {
    color: #0f172a;
    line-height: 1.25;
    margin: 1.5em 0 0.6em;
    font-weight: 700;
  }
  h1 { font-size: 1.75rem; margin-top: 0; }
  h2 { font-size: 1.35rem; }
  h3 { font-size: 1.1rem; }
  p {
    margin: 0 0 1em;
  }
  ul, ol {
    margin: 0 0 1em;
    padding-left: 1.5rem;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0 1.5em;
    font-size: 14px;
  }
  th, td {
    border: 1px solid #e2e8f0;
    padding: 10px 12px;
    vertical-align: top;
    text-align: left;
  }
  th {
    background: #f8fafc;
    font-weight: 600;
  }
  hr {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 1.5em 0;
  }
  strong, b {
    font-weight: 700;
  }
  .leo-preview-footer {
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
    color: #64748b;
  }
`;

function stripDocumentShell(html: string): string {
  const trimmed = html.trim();
  const bodyMatch = trimmed.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
  if (bodyMatch) {
    return bodyMatch[1].trim();
  }
  return trimmed
    .replace(/<!DOCTYPE[^>]*>/gi, "")
    .replace(/<\/?html[^>]*>/gi, "")
    .replace(/<head[\s\S]*?<\/head>/gi, "")
    .trim();
}

export function wrapClinicalPreviewHtml(html: string): string {
  const body = stripDocumentShell(html);
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>${CLINICAL_PREVIEW_CSS}</style>
</head>
<body>${body}</body>
</html>`;
}
