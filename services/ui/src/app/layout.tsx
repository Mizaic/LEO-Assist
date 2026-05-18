/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-4A8227DD
 *   Also implements: DO-5D525D34, DO-DB78C498
 *   DI: DI-522BBCC4, DI-61CB27B2, DI-985976A3
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-4A8227DD")
 */
import "./globals.css";
import "@/theme/tokens.css";
import type { Metadata } from "next";
import ThemeRegistry from "@/components/ThemeRegistry";
import { PipelineProvider } from "@/context/PipelineContext";
import { OrgProvider } from "@/context/OrgContext";
import { AnalyticsDateFilterProvider } from "@/context/AnalyticsDateFilterContext";
import { DensityProvider } from "@/context/DensityContext";
import { DemoModeProvider } from "@/context/DemoModeContext";
import AppShell from "@/components/AppShell";
import AuthProviderWrapper from "@/components/AuthProviderWrapper";
import RoleShellProvider from "@/components/RoleShellProvider";
import { dmSans, jetBrainsMono } from "@/lib/fonts";
import { fetchInitialSession } from "@/lib/serverSession";

// All UI pages are authenticated and per-user. Disable Next.js Full Route
// Cache so Cloudflare and the Next.js cache never serve a prerendered
// "loading" tree for an authenticated user (root cause of the post-login
// spinner observed in ACA / Cloudflare). See DI-LEO-AI-218.
export const dynamic = "force-dynamic";
export const revalidate = 0;
export const fetchCache = "force-no-store";

export const metadata: Metadata = {
  title: "LEO by Mizaic",
  description:
    "Clinical pathway audit intelligence by Mizaic -- for authorised Mizaic staff only",
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Resolve the session on the server so the first paint already reflects
  // the authenticated user. This eliminates the loading flash that was
  // previously cached and served by Cloudflare.
  const initialSession = await fetchInitialSession();

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
        <AuthProviderWrapper initialSession={initialSession}>
          <RoleShellProvider>
            <ThemeRegistry>
              <DensityProvider>
                <DemoModeProvider>
                  <OrgProvider>
                    <AnalyticsDateFilterProvider>
                      <PipelineProvider>
                        <AppShell>{children}</AppShell>
                      </PipelineProvider>
                    </AnalyticsDateFilterProvider>
                  </OrgProvider>
                </DemoModeProvider>
              </DensityProvider>
            </ThemeRegistry>
          </RoleShellProvider>
        </AuthProviderWrapper>
      </body>
    </html>
  );
}
