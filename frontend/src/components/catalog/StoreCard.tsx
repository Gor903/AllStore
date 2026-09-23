import Image from "next/image";

import type { CatalogStore } from "@/lib/api";
import { env } from "@/lib/env";
import { storeUrl } from "@/lib/urls";

const LOGO_SIZE = 40;

/** A shop lives on its own subdomain, so the link leaves this host — not a Next.js <Link>. */
export function StoreCard({ store }: { store: CatalogStore }) {
  return (
    <a
      href={storeUrl(store.subdomain)}
      className="flex flex-col gap-2 rounded-card border border-ink-muted/15 p-4 transition hover:border-brand/60"
    >
      <div className="flex items-center gap-3">
        {store.logo_url === null ? null : (
          <Image
            src={store.logo_url}
            alt=""
            width={LOGO_SIZE}
            height={LOGO_SIZE}
            unoptimized
            className="h-10 w-10 shrink-0 rounded-full object-cover"
          />
        )}
        <h3 className="text-lg font-medium">{store.display_name}</h3>
      </div>
      {store.description === null ? null : (
        <p className="line-clamp-3 text-sm text-ink-muted">{store.description}</p>
      )}
      <span className="mt-auto pt-2 text-sm text-ink-muted">
        {store.subdomain}.{env.baseDomain}
      </span>
    </a>
  );
}
