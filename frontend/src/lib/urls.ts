import { env } from "@/lib/env";

/**
 * Where everything lives.
 *
 * The marketplace domain advertises shops: it carries the catalogue, the search and the
 * shop list. A shop and its products live on the shop's own subdomain, and that is the
 * address a crawler is told about and a visitor is sent to. The marketplace address of a
 * product stays reachable and redirects there permanently, so older links keep working.
 */
export function storeUrl(subdomain: string, path: string = "/"): string {
  const base = new URL(env.siteUrl);
  // the port survives: locally the gateway does not sit on 80
  const port = base.port === "" ? "" : `:${base.port}`;
  return `${base.protocol}//${subdomain}.${env.baseDomain}${port}${path}`;
}

export function productPath(productId: string): string {
  return `/p/${encodeURIComponent(productId)}`;
}

/** The one address of a product: inside the shop that sells it. */
export function productUrl(subdomain: string, productId: string): string {
  return storeUrl(subdomain, productPath(productId));
}

export function siteUrl(path: string): string {
  return new URL(path, env.siteUrl).toString();
}

/**
 * Where a link points from the host the visitor is on. Inside the shop it stays relative —
 * no reason to send a browser to the address it is already at.
 */
export function productHref(
  subdomain: string,
  productId: string,
  currentSubdomain: string | null,
): string {
  return currentSubdomain === subdomain ? productPath(productId) : productUrl(subdomain, productId);
}

export function storeHref(subdomain: string, currentSubdomain: string | null): string {
  return currentSubdomain === subdomain ? "/" : storeUrl(subdomain);
}
