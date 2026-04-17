import "./globals.css";
import "@/theme/tokens.css";
import type { Metadata } from "next";
import ThemeRegistry from "@/components/ThemeRegistry";
import { PipelineProvider } from "@/context/PipelineContext";
import { OrgProvider } from "@/context/OrgContext";
import { AnalyticsDateFilterProvider } from "@/context/AnalyticsDateFilterContext";
import { DensityProvider } from "@/context/DensityContext";
import AppShell from "@/components/AppShell";
import AuthProviderWrapper from "@/components/AuthProviderWrapper";
import RoleShellProvider from "@/components/RoleShellProvider";
import { dmSans, jetBrainsMono } from "@/lib/fonts";

export const metadata: Metadata = {
  title: "LEO by Mizaic",
  description:
    "Clinical pathway audit intelligence by Mizaic -- for authorised Mizaic staff only",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      dir="ltr"
      className={`${dmSans.variable} ${jetBrainsMono.variable}`}
    >
      <body>
        <a href="#main-content" className="skip-link">
          Skip to main content
        </a>
        <AuthProviderWrapper>
          <RoleShellProvider>
            <ThemeRegistry>
              <DensityProvider>
                <OrgProvider>
                  <AnalyticsDateFilterProvider>
                    <PipelineProvider>
                      <AppShell>{children}</AppShell>
                    </PipelineProvider>
                  </AnalyticsDateFilterProvider>
                </OrgProvider>
              </DensityProvider>
            </ThemeRegistry>
          </RoleShellProvider>
        </AuthProviderWrapper>
      </body>
    </html>
  );
}
