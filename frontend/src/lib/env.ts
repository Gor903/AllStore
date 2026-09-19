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
} as const;
