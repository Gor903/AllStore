import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ImageManager } from "@/components/dashboard/ImageManager";
import { ProductActions } from "@/components/dashboard/ProductActions";
import { ProductForm } from "@/components/dashboard/ProductForm";
import { StatusPill } from "@/components/dashboard/StatusPill";
import { fetchCategories } from "@/lib/api";
import { getMyProduct, getMyStore, requireRole } from "@/lib/dal";
import { productStatus } from "@/lib/product-status";
import { productUrl } from "@/lib/urls";

export const metadata: Metadata = {
  title: "Товар",
  robots: { index: false, follow: false },
};

// the ceiling the backend enforces, see app/services/product_images.py
const MAX_IMAGES = 10;

export default async function EditProductPage({
  params,
}: PageProps<"/dashboard/products/[productId]">) {
  await requireRole("seller");
  const { productId } = await params;
  const [product, categories, store] = await Promise.all([
    getMyProduct(productId),
    fetchCategories(),
    getMyStore(),
  ]);
  // a product of another seller reads exactly as one that does not exist
  if (product === null) {
    notFound();
  }
  const status = productStatus(product);
  const live = product.publication_status === "published" && store !== null;

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 px-6 py-10">
      <nav className="text-sm text-ink-muted">
        <Link href="/dashboard" className="hover:text-brand">
          Кабинет
        </Link>
        {" / товар"}
      </nav>

      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{product.name}</h1>
          <StatusPill status={status} />
        </div>
        {status.hint === null ? null : <p className="text-sm text-ink-muted">{status.hint}</p>}
        {live ? (
          <a
            href={productUrl(store.subdomain, product.id)}
            target="_blank"
            rel="noreferrer"
            className="text-sm hover:text-brand"
          >
            Открыть в магазине
          </a>
        ) : null}
      </header>

      <ProductActions product={product} />

      <ImageManager productId={product.id} images={product.images} max={MAX_IMAGES} />

      <section className="flex flex-col gap-4">
        <h2 className="font-medium">Карточка товара</h2>
        <p className="text-sm text-ink-muted">
          Правка названия, описания или категории возвращает одобренный товар на повторную проверку.
          Цена и остаток проверку не сбрасывают.
        </p>
        <ProductForm categories={categories} product={product} />
      </section>
    </main>
  );
}
