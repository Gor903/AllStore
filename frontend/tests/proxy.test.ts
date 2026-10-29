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
    const response = proxy(request("/dashboard", "allstore_session=some-token"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("runs on every page, so no route can forget to ask for the headers", () => {
    expect(config.matcher).toHaveLength(1);
    const [rule] = config.matcher;

    expect(rule?.source).toContain("_next/static");
    // a prefetch renders nothing and would spend a nonce for nobody
    expect(rule?.missing).toEqual([
      { type: "header", key: "next-router-prefetch" },
      { type: "header", key: "purpose", value: "prefetch" },
    ]);
  });

  it("leaves a public page alone instead of sending it to the login form", () => {
    const response = proxy(request("/catalog"));

    expect(response.headers.get("location")).toBeNull();
  });

  it("sends an anonymous visitor away from the moderation queue", () => {
    const response = proxy(request("/moderation", ""));

    expect(response.headers.get("location")).toContain("/login");
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

  it("sends the cabinet back to the main domain from a storefront host", () => {
    // The session cookie is host-only (ADR 18), so there is none to find here. Serving the
    // page anyway produced a loop: bounce to /login, post to the apex, cookie lands on the
    // apex, come back to the subdomain, find nothing again.
    const response = proxy(request("/dashboard", "allstore_session=t", "cups.allstore.am"));

    const location = new URL(response.headers.get("location") ?? "");
    expect(location.hostname).toBe("allstore.am");
    expect(location.pathname).toBe("/dashboard");
  });

  it("sends the admin and moderation screens back too", () => {
    for (const path of ["/admin", "/moderation/products"]) {
      const response = proxy(request(path, undefined, "cups.allstore.am"));

      const location = new URL(response.headers.get("location") ?? "");
      expect(location.hostname).toBe("allstore.am");
      expect(location.pathname).toBe(path);
    }
  });

  it("carries the query string across", () => {
    const response = proxy(request("/moderation/products?page=3", undefined, "cups.allstore.am"));

    const location = new URL(response.headers.get("location") ?? "");
    expect(location.pathname).toBe("/moderation/products");
    expect(location.search).toBe("?page=3");
  });

  it("leaves everything else on the storefront host alone", () => {
    // a product page, a complaint, the login form: all of these work there, because the
    // browser sends the apex cookie to the apex API whatever page it is reading
    const response = proxy(request("/p/some-product", undefined, "cups.allstore.am"));

    expect(response.headers.get("location")).toBeNull();
    expect(rewriteTarget(response)).toBeNull();
  });
});

describe("security headers", () => {
  it("answers every page with a policy", () => {
    const headers = proxy(request("/catalog")).headers;

    expect(headers.get("content-security-policy")).toContain("default-src 'self'");
    expect(headers.get("x-content-type-options")).toBe("nosniff");
    expect(headers.get("x-frame-options")).toBe("DENY");
    expect(headers.get("referrer-policy")).toBe("no-referrer");
  });

  it("refuses to be framed, which is what clickjacking needs", () => {
    const policy = proxy(request("/dashboard", "allstore_session=t")).headers.get(
      "content-security-policy",
    );

    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("object-src 'none'");
    expect(policy).toContain("base-uri 'self'");
    expect(policy).toContain("form-action 'self'");
  });

  it("gives each request its own nonce", () => {
    const first = proxy(request("/catalog")).headers.get("content-security-policy") ?? "";
    const second = proxy(request("/catalog")).headers.get("content-security-policy") ?? "";

    const nonceOf = (policy: string) => /'nonce-([^']+)'/.exec(policy)?.[1];
    expect(nonceOf(first)).toBeDefined();
    expect(nonceOf(first)).not.toBe(nonceOf(second));
  });

  it("carries the policy on a refusal too, not only on a page that renders", () => {
    const response = proxy(request("/admin"));

    expect(response.status).toBe(307);
    expect(response.headers.get("content-security-policy")).toContain("frame-ancestors 'none'");
  });

  it("allows a storefront's own colours, which live in a style attribute", () => {
    const policy = proxy(request("/catalog")).headers.get("content-security-policy") ?? "";

    expect(policy).toContain("style-src 'self' 'unsafe-inline'");
  });
});
