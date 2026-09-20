import "server-only";

import { headers } from "next/headers";

import { env } from "@/lib/env";
import { subdomainFromHost } from "@/lib/hosts";

/**
 * The storefront the visitor is currently on, or null on the marketplace itself.
 * A page uses it to decide whether a link has to leave the host it is rendered on.
 */
export async function currentSubdomain(): Promise<string | null> {
  return subdomainFromHost((await headers()).get("host"), env.baseDomain);
}
