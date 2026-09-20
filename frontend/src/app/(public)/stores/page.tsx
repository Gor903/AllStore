import type { Metadata } from "next";
import Link from "next/link";

import { SiteHeader } from "@/components/SiteHeader";
import { Pagination } from "@/components/catalog/Pagination";
import { PAGE_SIZE, fetchCatalogStores } from "@/lib/api";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Магазины",
  description: "Магазины площадки AllStore.am.",
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
                <Link
                  key={store.subdomain}
                  href={`/s/${encodeURIComponent(store.subdomain)}`}
                  className="flex flex-col gap-2 rounded-card border border-ink-muted/15 p-4 transition hover:border-brand/60"
                >
                  <h2 className="text-lg font-medium">{store.display_name}</h2>
                  {store.description === null ? null : (
                    <p className="line-clamp-3 text-sm text-ink-muted">{store.description}</p>
                  )}
                  <span className="mt-auto pt-2 text-sm text-ink-muted">{store.subdomain}</span>
                </Link>
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
