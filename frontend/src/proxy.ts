import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/lib/env";
import { subdomainFromHost } from "@/lib/hosts";

/**
 * Two jobs, in order: send a storefront subdomain to its page, then the optimistic
 * session check. The latter is presence of the cookie only, no backend call — proxy runs
 * on every matched request including prefetches, so the real check lives next to the data
 * in src/lib/dal.ts.
 */
export function proxy(request: NextRequest): NextResponse {
  const subdomain = subdomainFromHost(request.headers.get("host"), env.baseDomain);
  // only the root: /login and the cabinet stay reachable on a storefront host
  if (subdomain !== null && request.nextUrl.pathname === "/") {
    return NextResponse.rewrite(new URL(`/s/${subdomain}`, request.url));
  }
  if (request.nextUrl.pathname === "/" || request.cookies.has(env.accessCookie)) {
    return NextResponse.next();
  }
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/", "/dashboard/:path*", "/admin/:path*"],
};
