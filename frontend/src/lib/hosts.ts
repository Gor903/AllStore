const LABEL = /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/;

/** Hosts that serve the marketplace itself. The full reserved list lives in backend settings. */
const MARKETPLACE_LABELS = new Set(["www"]);

/**
 * The storefront label of a Host header, or null when the host is not a storefront.
 * Mirrors app/core/hosts.py on the backend — the proxy has to route before it can ask.
 */
export function subdomainFromHost(host: string | null, baseDomain: string): string | null {
  // an IPv6 literal is never a storefront, and its colons would confuse the port split
  if (host === null || host === "" || host.startsWith("[")) {
    return null;
  }
  const name = (host.trim().toLowerCase().split(":")[0] ?? "").trim();
  const suffix = `.${baseDomain.trim().toLowerCase()}`;
  if (!name.endsWith(suffix)) {
    return null;
  }
  const label = name.slice(0, -suffix.length);
  // a dot left over means a deeper level (a.b.allstore.am), which we do not route
  if (label.includes(".") || !LABEL.test(label) || MARKETPLACE_LABELS.has(label)) {
    return null;
  }
  return label;
}
