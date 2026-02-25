import "./globals.css";
import type { Metadata } from "next";
import ThemeRegistry from "@/components/ThemeRegistry";
import { PipelineProvider } from "@/context/PipelineContext";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Clinical Coding Review",
  description: "Training Creator HITL MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <ThemeRegistry>
          <PipelineProvider>
            <AppShell>{children}</AppShell>
          </PipelineProvider>
        </ThemeRegistry>
      </body>
    </html>
  );
}
