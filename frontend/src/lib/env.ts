const isServer = typeof window === "undefined";

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
  baseDomain: process.env["NEXT_PUBLIC_BASE_DOMAIN"] ?? "allstore.am",
  // must match access_cookie_name / csrf_cookie_name in backend settings
  accessCookie: process.env["NEXT_PUBLIC_ACCESS_COOKIE"] ?? "allstore_access",
  csrfCookie: process.env["NEXT_PUBLIC_CSRF_COOKIE"] ?? "allstore_csrf",
  csrfHeader: "X-CSRF-Token",
} as const;

export const API_PREFIX = "/api/v1";
