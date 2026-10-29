const isServer = typeof window === "undefined";

const baseDomain = process.env["NEXT_PUBLIC_BASE_DOMAIN"] ?? "allstore.am";

/**
 * Reads public runtime config once, so no component hardcodes an endpoint.
 * Server-side rendering talks to the backend over the internal network, the browser
 * goes through the public gateway — hence two different base URLs.
 */
export const env = {
  apiUrl:
    (isServer ? process.env["INTERNAL_API_URL"] : undefined) ??
    process.env["NEXT_PUBLIC_API_URL"] ??
    "http://localhost:8080",
  baseDomain,
  // absolute addresses for canonical links, Open Graph and the sitemap; a crawler is
  // given the public address of the site, not the one the container answers on
  siteUrl: process.env["NEXT_PUBLIC_SITE_URL"] ?? `https://${baseDomain}`,
  // Must match what the backend sets — `access_cookie` / `csrf_cookie` in core/config.py,
  // which outside local carry the `__Host-` prefix the browser needs before it will keep a
  // cookie host-only. The defaults here are the local ones, where plain http rules it out.
  accessCookie: process.env["NEXT_PUBLIC_ACCESS_COOKIE"] ?? "allstore_access",
  csrfCookie: process.env["NEXT_PUBLIC_CSRF_COOKIE"] ?? "allstore_csrf",
  csrfHeader: "X-CSRF-Token",
} as const;

export const API_PREFIX = "/api/v1";
