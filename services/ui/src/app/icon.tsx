/**
 * Browser-tab favicon -- same LeoO mark as the in-app loading icon.
 */
export const size = { width: 512, height: 512 };
export const contentType = "image/svg+xml";

const RING =
  "M106.508 20.9663C106.547 21.3824 106.577 22.1104 106.577 22.5378C106.577 29.8809 100.675 35.798 93.3446 35.798C86.0147 35.798 80.0722 29.8449 80.0722 22.5019C80.0722 15.1588 86.0147 9.20575 93.3446 9.20575C94.2281 9.20575 95.0889 9.29652 95.9232 9.46104L98.6623 0.601362C96.8992 0.156959 95.2437 0 93.3446 0C80.9406 0 70.8848 10.0738 70.8848 22.5C70.8848 34.9262 80.9406 45 93.3446 45C105.749 45 115.805 34.9262 115.805 22.5C115.805 21.3899 115.721 20.2988 115.567 19.2322L106.509 20.9644L106.508 20.9663Z";
const ACCENT =
  "M99.8359 10.9118C102.224 12.2564 104.051 14.3252 105.352 16.8763L114.383 14.5635C112.344 9.11531 108.385 4.87931 103.064 2.21289L99.8359 10.9118Z";

export default function Icon() {
  const svg = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="70.8848 0 44.9202 45"',
    ' width="512" height="512" fill="none">',
    `<path d="${RING}" fill="#00093b"/>`,
    `<path d="${ACCENT}" fill="#d758ff"/>`,
    "</svg>",
  ].join("");
  return new Response(svg, {
    headers: { "Content-Type": "image/svg+xml" },
  });
}
