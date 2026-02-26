import "./globals.css";
import type { Metadata } from "next";
import ThemeRegistry from "@/components/ThemeRegistry";
import { PipelineProvider } from "@/context/PipelineContext";
import AppShell from "@/components/AppShell";
import SessionProviderWrapper from "@/components/SessionProviderWrapper";

export const metadata: Metadata = {
  title: "Clinical Audit Platform",
  description: "Primary Care Audit — Clinical Coding, Episodes, Analytics & Reports",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <SessionProviderWrapper>
          <ThemeRegistry>
            <PipelineProvider>
              <AppShell>{children}</AppShell>
            </PipelineProvider>
          </ThemeRegistry>
        </SessionProviderWrapper>
      </body>
    </html>
  );
}
