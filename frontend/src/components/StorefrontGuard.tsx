"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { STORE_BLOCKED_CODE } from "@/lib/api-codes";
import { apiGet } from "@/lib/browser-api";

/**
 * Asks the marketplace whether this shop is open to whoever is reading, and hides it if not.
 *
 * It has to be the browser that asks, and it has to ask the apex. A shop lives on its own
 * subdomain, the session cookie is host-only, and so the server rendering `cups.allstore.am`
 * has no idea who is looking — to it every visitor is a stranger, and a stranger is nobody's
 * barred customer. The one party that knows is the browser, and the one address that will
 * tell it is the one holding the cookie.
 *
 * The page is rendered first and withdrawn after, rather than held back until the answer
 * arrives. A shop's storefront is public and has to stay server-rendered for search engines;
 * waiting on a round trip before showing anything would cost every visitor a blank screen to
 * spare one person a glimpse of a shop they were told they may not use.
 */
export function StorefrontGuard({
  subdomain,
  children,
}: {
  subdomain: string;
  children: ReactNode;
}) {
  const [barred, setBarred] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const result = await apiGet(`/storefront/${encodeURIComponent(subdomain)}`);
      // only this one answer hides the shop; a network hiccup leaves it as it is
      if (!cancelled && !result.ok && result.error.code === STORE_BLOCKED_CODE) {
        setBarred(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subdomain]);

  if (!barred) {
    return <>{children}</>;
  }

  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-6 py-16">
      <h1 className="text-2xl font-semibold">Магазин ограничил вам доступ</h1>
      <p className="text-ink-muted">
        Продавец закрыл этот магазин для вашего аккаунта. Остальная площадка работает как обычно:
        каталог, другие магазины и жалобы по-прежнему вам доступны.
      </p>
      <Link href="/catalog" className="self-start text-brand">
        Вернуться в каталог
      </Link>
    </main>
  );
}
