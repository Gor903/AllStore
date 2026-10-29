import Link from "next/link";

import { API_PREFIX, env } from "@/lib/env";

/**
 * A plain link, not a fetch.
 *
 * The journey to Google is a top-level navigation by nature: the browser has to show
 * Google's own page at Google's own address, and a request made in the background cannot do
 * that. The role travels in the query string and is read on our side from the sealed cookie
 * instead, so editing it here buys nothing.
 */
export function GoogleButton({ role }: { role: "buyer" | "seller" }) {
  const href = `${env.apiUrl}${API_PREFIX}/auth/google/start?role=${role}`;

  return (
    <Link
      href={href}
      prefetch={false}
      className="flex items-center justify-center gap-2 rounded-lg border border-ink-muted/30 px-4 py-2 text-sm font-medium hover:border-brand hover:text-brand"
    >
      Продолжить с Google
    </Link>
  );
}
