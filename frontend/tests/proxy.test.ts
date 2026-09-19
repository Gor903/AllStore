import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { config, proxy } from "@/proxy";

function request(path: string, cookie?: string, host?: string): NextRequest {
  const headers: Record<string, string> = {};
  if (cookie !== undefined) {
    headers["cookie"] = cookie;
  }
  if (host !== undefined) {
    headers["host"] = host;
  }
  return new NextRequest(`http://localhost:3000${path}`, { headers });
}

function rewriteTarget(response: Response): string | null {
  const rewrite = response.headers.get("x-middleware-rewrite");
  return rewrite === null ? null : new URL(rewrite).pathname;
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

  it("runs on the root as well as the protected areas", () => {
    expect(config.matcher).toEqual(["/", "/dashboard/:path*", "/admin/:path*"]);
  });
});

describe("proxy on a storefront subdomain", () => {
  it("rewrites the root to the storefront page", () => {
    const response = proxy(request("/", undefined, "cups.allstore.am"));

    expect(rewriteTarget(response)).toBe("/s/cups");
  });

  it("keeps the marketplace home on the apex domain", () => {
    const response = proxy(request("/", undefined, "allstore.am"));

    expect(rewriteTarget(response)).toBeNull();
    expect(response.headers.get("location")).toBeNull();
  });

  it("keeps the marketplace home on www", () => {
    const response = proxy(request("/", undefined, "www.allstore.am"));

    expect(rewriteTarget(response)).toBeNull();
  });

  it("does not send an anonymous visitor of the marketplace root to the login page", () => {
    const response = proxy(request("/", undefined, "allstore.am"));

    expect(response.status).toBe(200);
  });

  it("leaves the cabinet reachable on a storefront host", () => {
    const response = proxy(request("/dashboard", "allstore_access=t", "cups.allstore.am"));

    expect(rewriteTarget(response)).toBeNull();
    expect(response.headers.get("location")).toBeNull();
  });
});
