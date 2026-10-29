const isServer = typeof window === "undefined";

/**
 * The first of these that is actually set to something.
 *
 * `??` was not enough: it falls through on `undefined` and stops on an empty string, and an
 * empty string is exactly what a deploy produces when a variable is declared and left blank.
 * The consequence was not a crash but something quieter — `apiUrl` would become "" and every
 * browser request would go to whatever host the page was served from. On a storefront
 * subdomain that is not the API, so a signed-in buyer's complaint would arrive with no author.
 */
function firstSet(...candidates: (string | undefined)[]): string | undefined {
  return candidates.find((value) => value !== undefined && value.trim() !== "");
}

const baseDomain = firstSet(process.env["NEXT_PUBLIC_BASE_DOMAIN"]) ?? "allstore.am";

/**
 * Reads public runtime config once, so no component hardcodes an endpoint.
 * Server-side rendering talks to the backend over the internal network, the browser
 * goes through the public gateway — hence two different base URLs.
 */
export const env = {
  apiUrl:
    firstSet(
      isServer ? process.env["INTERNAL_API_URL"] : undefined,
      process.env["NEXT_PUBLIC_API_URL"],
    ) ?? "http://localhost:8080",
  baseDomain,
  // absolute addresses for canonical links, Open Graph and the sitemap; a crawler is
  // given the public address of the site, not the one the container answers on
  siteUrl: firstSet(process.env["NEXT_PUBLIC_SITE_URL"]) ?? `https://${baseDomain}`,
  // Must match what the backend sets — `session_cookie` / `csrf_cookie` in core/config.py,
  // which outside local carry the `__Host-` prefix the browser needs before it will keep a
  // cookie host-only. The defaults here are the local ones, where plain http rules it out.
  sessionCookie: firstSet(process.env["NEXT_PUBLIC_SESSION_COOKIE"]) ?? "allstore_session",
  csrfCookie: firstSet(process.env["NEXT_PUBLIC_CSRF_COOKIE"]) ?? "allstore_csrf",
  csrfHeader: "X-CSRF-Token",
} as const;

export const API_PREFIX = "/api/v1";
