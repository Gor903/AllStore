import Image from "next/image";
import Link from "next/link";

import { siteUrl } from "@/lib/urls";

type StoreHeaderProps = {
  displayName: string;
  /** Null on the marketplace host, where the shop root is somewhere else entirely. */
  homeHref: string;
  logoUrl?: string | null;
};

const LOGO_SIZE = 40;

/** What a shop wears on its own subdomain: its name, its mark, and a way back. */
export function StoreHeader({ displayName, homeHref, logoUrl = null }: StoreHeaderProps) {
  return (
    <header className="border-b border-ink-muted/15">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
        <Link
          href={homeHref}
          className="flex items-center gap-3 text-xl font-semibold tracking-tight"
        >
          {logoUrl === null ? null : (
            <Image
              src={logoUrl}
              alt=""
              width={LOGO_SIZE}
              height={LOGO_SIZE}
              unoptimized
              className="h-10 w-10 rounded-full object-cover"
            />
          )}
          {displayName}
        </Link>
        <a href={siteUrl("/catalog")} className="ml-auto text-sm text-ink-muted hover:text-brand">
          Весь каталог AllStore.am
        </a>
      </div>
    </header>
  );
}
