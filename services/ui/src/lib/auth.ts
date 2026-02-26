/**
 * NextAuth v5 configuration with Microsoft Entra ID (Azure AD).
 *
 * Ported from VRB frontend/lib/auth/auth.ts.
 * Provides JWT-based sessions with access tokens passed downstream.
 */
import NextAuth from "next-auth";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    MicrosoftEntraID({
      clientId: process.env.AZURE_AD_CLIENT_ID ?? "",
      clientSecret: process.env.AZURE_AD_CLIENT_SECRET ?? "",
      tenantId: process.env.AZURE_AD_TENANT_ID ?? "",
      authorization: {
        params: {
          scope: `openid profile email api://${process.env.AZURE_AD_CLIENT_ID}/access_as_user`,
        },
      },
    }),
  ],
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.access_token) {
        token.accessToken = account.access_token;
      }
      return token;
    },
    async session({ session, token }) {
      (session as any).accessToken = token.accessToken;
      return session;
    },
    authorized({ auth: session, request }) {
      const isLoggedIn = !!session?.user;
      const isProtected = request.nextUrl.pathname.startsWith("/dashboard") ||
        request.nextUrl.pathname.startsWith("/episodes") ||
        request.nextUrl.pathname.startsWith("/css") ||
        request.nextUrl.pathname.startsWith("/reports") ||
        request.nextUrl.pathname.startsWith("/patients") ||
        request.nextUrl.pathname.startsWith("/pipeline");
      if (isProtected && !isLoggedIn) return false;
      return true;
    },
  },
  pages: {
    signIn: "/",
  },
});
