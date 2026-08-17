/**
 * Post-login destination -- platform admins open Knowledge.
 *
 * Design Controls: DI-FAF97A8C, DI-09DF0A10.
 */
import { landingForRole } from "@leo/design-system";

import { postLoginPath } from "@/lib/postLoginPath";

describe("postLoginPath", () => {
  it("sends platform_admin to Knowledge", () => {
    expect(landingForRole("platform_admin")).toBe("/admin/knowledge");
    expect(
      postLoginPath({ selectedRole: "platform_admin", isPlatformAdmin: true }),
    ).toBe("/admin/knowledge");
  });

  it("sends a platform admin with no selected role to Knowledge", () => {
    expect(postLoginPath({ selectedRole: null, isPlatformAdmin: true })).toBe(
      "/admin/knowledge",
    );
  });

  it("keeps other roles on their own landing", () => {
    expect(
      postLoginPath({ selectedRole: "triage_clinician", isPlatformAdmin: false }),
    ).toBe("/care/patients");
    expect(
      postLoginPath({ selectedRole: null, isPlatformAdmin: false }),
    ).toBe("/care/dashboard");
  });
});
