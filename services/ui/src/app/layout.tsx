import "./globals.css";
import type { Metadata } from "next";
import ThemeRegistry from "@/components/ThemeRegistry";
import { PipelineProvider } from "@/context/PipelineContext";
import { OrgProvider } from "@/context/OrgContext";
import AppShell from "@/components/AppShell";
import AuthProviderWrapper from "@/components/AuthProviderWrapper";

export const metadata: Metadata = {
  title: "LEO for Primary Care",
  description: "Referral quality review, safety netting, early diagnosis and screening — powered by Mizaic",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <AuthProviderWrapper>
          <ThemeRegistry>
            <OrgProvider>
              <PipelineProvider>
                <AppShell>{children}</AppShell>
              </PipelineProvider>
            </OrgProvider>
          </ThemeRegistry>
        </AuthProviderWrapper>
      </body>
    </html>
  );
}
