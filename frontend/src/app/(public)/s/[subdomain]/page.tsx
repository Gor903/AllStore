import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Pagination } from "@/components/catalog/Pagination";
import { ProductCard } from "@/components/catalog/ProductCard";
import { PAGE_SIZE, fetchCatalogProducts, fetchStorefront } from "@/lib/api";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: PageProps<"/s/[subdomain]">): Promise<Metadata> {
  const { subdomain } = await params;
  const store = await fetchStorefront(subdomain);
  if (store === null) {
    return { title: "Магазин не найден" };
  }
  return {
    title: store.display_name,
    description: store.description?.slice(0, 160) ?? `Магазин ${store.display_name} на AllStore.am`,
  };
}

export default async function StorefrontPage({
  params,
  searchParams,
}: PageProps<"/s/[subdomain]">) {
  const { subdomain } = await params;
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const store = await fetchStorefront(subdomain);
  if (store === null) {
    notFound();
  }
  // the storefront shows the same catalogue narrowed to one shop, so the visibility rules
  // are the ones the catalogue already enforces
  const page = await fetchCatalogProducts({ q: null, category: null, store: subdomain, offset });

  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <div
        className="h-2 w-24 rounded-full bg-brand"
        style={store.primary_color === null ? undefined : { background: store.primary_color }}
      />
      <header className="flex flex-col gap-2">
        <h1 className="text-4xl font-semibold tracking-tight">{store.display_name}</h1>
        {store.description === null ? null : <p className="text-ink-muted">{store.description}</p>}
      </header>

      {page === null ? (
        <p className="text-danger">Товары сейчас недоступны, попробуйте обновить страницу.</p>
      ) : page.items.length === 0 ? (
        <p className="text-ink-muted">В этом магазине пока нет товаров.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {page.items.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
          <Pagination
            path={`/s/${encodeURIComponent(subdomain)}`}
            params={new URLSearchParams()}
            offset={offset}
            pageSize={PAGE_SIZE}
            total={page.total}
          />
        </>
      )}

      <p className="text-sm text-ink-muted">
        <Link href="/catalog" className="hover:text-brand">
          Весь каталог AllStore.am
        </Link>
      </p>
    </main>
  );
}
