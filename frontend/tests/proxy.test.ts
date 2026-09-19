import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, proxy } from "@/proxy";

function request(path: string, cookie?: string): NextRequest {
  return new NextRequest(`http://localhost:3000${path}`, {
    headers: cookie ? { cookie } : {},
  });
}

describe("proxy", () => {
  it("sends an anonymous visitor to the login page", () => {
    const response = proxy(request("/dashboard"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/dashboard");
  });

  it("protects the admin area the same way", () => {
    const response = proxy(request("/admin"));

    expect(new URL(response.headers.get("location") ?? "").pathname).toBe("/login");
  });

  it("lets a request with a session cookie through", () => {
    const response = proxy(request("/dashboard", "allstore_access=some-token"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("runs only on the protected areas", () => {
    expect(config.matcher).toEqual(["/dashboard/:path*", "/admin/:path*"]);
  });
});
