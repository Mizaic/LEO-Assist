import "./globals.css";
import type { Metadata } from "next";
import ThemeRegistry from "@/components/ThemeRegistry";
import { PipelineProvider } from "@/context/PipelineContext";
import { OrgProvider } from "@/context/OrgContext";
import { AnalyticsDateFilterProvider } from "@/context/AnalyticsDateFilterContext";
import AppShell from "@/components/AppShell";
import AuthProviderWrapper from "@/components/AuthProviderWrapper";

export const metadata: Metadata = {
  title: "LEO by Mizaic",
  description: "Clinical pathway audit intelligence by Mizaic -- for authorised Mizaic staff only",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <AuthProviderWrapper>
          <ThemeRegistry>
            <OrgProvider>
              <AnalyticsDateFilterProvider>
                <PipelineProvider>
                  <AppShell>{children}</AppShell>
                </PipelineProvider>
              </AnalyticsDateFilterProvider>
            </OrgProvider>
          </ThemeRegistry>
        </AuthProviderWrapper>
      </body>
    </html>
  );
}
