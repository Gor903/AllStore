import type { Metadata } from "next";
import Image from "next/image";

import { SiteHeader } from "@/components/SiteHeader";
import { Pagination } from "@/components/catalog/Pagination";
import { PAGE_SIZE, fetchCatalogStores } from "@/lib/api";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { env } from "@/lib/env";
import { storeUrl } from "@/lib/urls";

export const dynamic = "force-dynamic";

const LOGO_SIZE = 40;

export const metadata: Metadata = {
  title: "Магазины",
  description: "Магазины площадки AllStore.am.",
  alternates: { canonical: "/stores" },
};

export default async function StoresPage({ searchParams }: PageProps<"/stores">) {
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const page = await fetchCatalogStores(offset);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        <h1 className="text-3xl font-semibold tracking-tight">Магазины</h1>

        {page === null ? (
          <p className="text-danger">Список сейчас недоступен, попробуйте обновить страницу.</p>
        ) : page.items.length === 0 ? (
          <p className="text-ink-muted">Пока ни один магазин не открыт.</p>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {page.items.map((store) => (
                <a
                  key={store.subdomain}
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
                    <h2 className="text-lg font-medium">{store.display_name}</h2>
                  </div>
                  {store.description === null ? null : (
                    <p className="line-clamp-3 text-sm text-ink-muted">{store.description}</p>
                  )}
                  <span className="mt-auto pt-2 text-sm text-ink-muted">
                    {store.subdomain}.{env.baseDomain}
                  </span>
                </a>
              ))}
            </div>
            <Pagination
              path="/stores"
              params={new URLSearchParams()}
              offset={offset}
              pageSize={PAGE_SIZE}
              total={page.total}
            />
          </>
        )}
      </main>
    </>
  );
}
