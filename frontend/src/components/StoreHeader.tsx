import Link from "next/link";

import { siteUrl } from "@/lib/urls";

type StoreHeaderProps = {
  displayName: string;
  /** Null on the marketplace host, where the shop root is somewhere else entirely. */
  homeHref: string;
};

/** What a shop wears on its own subdomain: its name, and a way back to the marketplace. */
export function StoreHeader({ displayName, homeHref }: StoreHeaderProps) {
  return (
    <header className="border-b border-ink-muted/15">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
        <Link href={homeHref} className="text-xl font-semibold tracking-tight">
          {displayName}
        </Link>
        <a href={siteUrl("/catalog")} className="ml-auto text-sm text-ink-muted hover:text-brand">
          Весь каталог AllStore.am
        </a>
      </div>
    </header>
  );
}
