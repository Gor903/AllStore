import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/lib/env";
import { subdomainFromHost } from "@/lib/hosts";

/**
 * Three jobs, in order: the security headers every page answers with, the storefront
 * subdomain rewrite, and the optimistic session check.
 *
 * The last is presence of the cookie only, no backend call — this runs on every matched
 * request including prefetches, so the real check lives next to the data in src/lib/dal.ts.
 */

/** Only these are guarded. Everything else is matched for the headers and let through. */
const GUARDED = ["/dashboard", "/admin", "/moderation"];

const DEVELOPMENT = process.env.NODE_ENV === "development";

function isGuarded(pathname: string): boolean {
  return GUARDED.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/**
 * A fresh nonce per request, which is what makes `strict-dynamic` worth having: an injected
 * script cannot run without one, and it cannot guess one.
 *
 * Next.js reads it back out of the header we set and attaches it to its own scripts, so no
 * tag has to carry it by hand. That only works on a page rendered per request — every route
 * in this application is except the 404, whose scripts are refused. It still renders and its
 * links still navigate, because a `Link` is an anchor before it is anything else.
 */
function securityHeaders(nonce: string): Record<string, string> {
  const policy = [
    "default-src 'self'",
    // 'unsafe-eval' is React rebuilding server stacks in the browser; it is development-only
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${DEVELOPMENT ? " 'unsafe-eval'" : ""}`,
    // a nonce cannot cover a `style` attribute, and four components set one — a shop's own
    // colours, the admin's bars. Inline styles are a far weaker vector than inline scripts,
    // and refusing them here would cost every storefront its identity
    "style-src 'self' 'unsafe-inline'",
    // product photos come from the object store, whose host differs per environment; naming
    // it here would be one more value a deploy can get wrong and lose every photo to
    `img-src 'self' blob: data: https:${DEVELOPMENT ? " http:" : ""}`,
    `connect-src 'self' ${env.apiUrl}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (!DEVELOPMENT) {
    policy.push("upgrade-insecure-requests");
  }
  const headers: Record<string, string> = {
    "Content-Security-Policy": policy.join("; "),
    "X-Content-Type-Options": "nosniff",
    // the reset link carries a token in the URL, and a referrer is how it leaks to whatever
    // the page links out to
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
  };
  if (!DEVELOPMENT) {
    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload";
  }
  return headers;
}

function withHeaders(response: NextResponse, headers: Record<string, string>): NextResponse {
  for (const [name, value] of Object.entries(headers)) {
    response.headers.set(name, value);
  }
  return response;
}

export function proxy(request: NextRequest): NextResponse {
  const nonce = crypto.randomUUID().replaceAll("-", "");
  const headers = securityHeaders(nonce);
  // Next.js takes the nonce from the request copy it renders with, so the policy has to
  // travel inwards as well as back out
  const forwarded = new Headers(request.headers);
  forwarded.set("x-nonce", nonce);
  forwarded.set("Content-Security-Policy", headers["Content-Security-Policy"] ?? "");
  const carryOn = (): NextResponse => NextResponse.next({ request: { headers: forwarded } });

  const subdomain = subdomainFromHost(request.headers.get("host"), env.baseDomain);
  // only the root: /login and the cabinet stay reachable on a storefront host
  if (subdomain !== null && request.nextUrl.pathname === "/") {
    const storefront = NextResponse.rewrite(new URL(`/s/${subdomain}`, request.url), {
      request: { headers: forwarded },
    });
    return withHeaders(storefront, headers);
  }
  if (!isGuarded(request.nextUrl.pathname) || request.cookies.has(env.accessCookie)) {
    return withHeaders(carryOn(), headers);
  }
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return withHeaders(NextResponse.redirect(loginUrl), headers);
}

export const config = {
  matcher: [
    // every page, so the headers are not something a route can forget to ask for. The API is
    // the backend's own answer and carries its own; the rest are files with nothing to
    // execute. Prefetches are skipped: they render nothing and would spend a nonce each
    {
      source: "/((?!api|_next/static|_next/image|favicon.ico|icon.svg|robots.txt|sitemap.xml).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
