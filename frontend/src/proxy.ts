import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/lib/env";

/**
 * Optimistic check only: presence of the session cookie, no backend call.
 * Proxy runs on every matched request including prefetches, so the real check
 * lives next to the data in src/lib/dal.ts.
 */
export function proxy(request: NextRequest): NextResponse {
  if (request.cookies.has(env.accessCookie)) {
    return NextResponse.next();
  }
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", request.nextUrl.pathname);
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/dashboard/:path*", "/admin/:path*"],
};
