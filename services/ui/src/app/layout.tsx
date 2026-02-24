import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Clinical Coding Review",
  description: "Training Creator HITL MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
