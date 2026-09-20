import type { Metadata } from "next";
import Link from "next/link";

import { SiteHeader } from "@/components/SiteHeader";
import { ProductCard } from "@/components/catalog/ProductCard";
import { fetchCatalogProducts } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: { absolute: "AllStore.am — магазины Армении в одном каталоге" },
  description:
    "Каталог товаров армянских магазинов: поиск по категориям, витрина у каждого продавца, связь напрямую.",
  alternates: { canonical: "/" },
};

const FRESH_COUNT = 8;

export default async function HomePage() {
  const page = await fetchCatalogProducts({ q: null, category: null, store: null, offset: 0 });
  const fresh = page?.items.slice(0, FRESH_COUNT) ?? [];

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
        <section className="flex flex-col gap-4">
          <h1 className="text-4xl font-semibold tracking-tight">Магазины Армении в одном месте</h1>
          <p className="max-w-2xl text-ink-muted">
            Найдите товар в общем каталоге и напишите продавцу напрямую. Свой магазин с собственным
            адресом открывается за пару минут.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/catalog" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
              Смотреть каталог
            </Link>
            <Link
              href="/register"
              className="rounded-lg border border-ink-muted/30 px-4 py-2 font-medium"
            >
              Открыть магазин
            </Link>
          </div>
        </section>

        {fresh.length === 0 ? null : (
          <section className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-semibold tracking-tight">Новые товары</h2>
              <Link href="/catalog" className="text-sm hover:text-brand">
                Весь каталог
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
              {fresh.map((product) => (
                <ProductCard key={product.id} product={product} />
              ))}
            </div>
          </section>
        )}
      </main>
    </>
  );
}
