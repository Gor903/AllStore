import type { Metadata } from "next";

import { SiteHeader } from "@/components/SiteHeader";
import { CatalogFilters } from "@/components/catalog/CatalogFilters";
import { Pagination } from "@/components/catalog/Pagination";
import { ProductCard } from "@/components/catalog/ProductCard";
import { PAGE_SIZE, fetchCatalogProducts, fetchCategories } from "@/lib/api";
import { catalogSearchParams, parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { currentSubdomain } from "@/lib/request-host";
import { productHref } from "@/lib/urls";

// rendered per request: the catalogue changes whenever a moderator approves something
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Каталог",
  description: "Товары магазинов AllStore.am — поиск по названию и категориям.",
  // every combination of filters is its own address; the bare catalogue is the one
  // worth indexing, the rest point at it
  alternates: { canonical: "/catalog" },
};

export default async function CatalogPage({ searchParams }: PageProps<"/catalog">) {
  const query = parseCatalogQuery(toSearchParams(await searchParams));
  const [page, categories, subdomain] = await Promise.all([
    fetchCatalogProducts(query),
    fetchCategories(),
    currentSubdomain(),
  ]);

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
        <h1 className="text-3xl font-semibold tracking-tight">Каталог</h1>
        <CatalogFilters categories={categories} query={query} />

        {page === null ? (
          <p className="text-danger">Каталог сейчас недоступен, попробуйте обновить страницу.</p>
        ) : page.items.length === 0 ? (
          <p className="text-ink-muted">
            По этому запросу ничего не нашлось. Попробуйте другое слово или категорию.
          </p>
        ) : (
          <>
            <p className="text-sm text-ink-muted">Найдено товаров: {page.total}</p>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {page.items.map((product) => (
                <ProductCard
                  key={product.id}
                  product={product}
                  href={productHref(product.store.subdomain, product.id, subdomain)}
                />
              ))}
            </div>
            <Pagination
              path="/catalog"
              params={catalogSearchParams(query)}
              offset={query.offset}
              pageSize={PAGE_SIZE}
              total={page.total}
            />
          </>
        )}
      </main>
    </>
  );
}
