import { env } from "@/lib/env";

/**
 * One canonical address per thing, so a crawler never sees the same page twice.
 *
 * A storefront is reachable both as a subdomain and as /s/{subdomain} on the marketplace.
 * The subdomain wins: it is the address the seller is given and the one they hand out.
 * A product lives on the marketplace only — the weight of every shop then lands on one
 * domain instead of being scattered across hundreds of subdomains.
 */
export function storeUrl(subdomain: string): string {
  const scheme = new URL(env.siteUrl).protocol;
  return `${scheme}//${subdomain}.${env.baseDomain}/`;
}

export function productUrl(productId: string): string {
  return new URL(`/p/${encodeURIComponent(productId)}`, env.siteUrl).toString();
}

export function siteUrl(path: string): string {
  return new URL(path, env.siteUrl).toString();
}
