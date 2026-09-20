import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteHeader } from "@/components/SiteHeader";
import { fetchCatalogProduct } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { productUrl } from "@/lib/urls";

export const dynamic = "force-dynamic";

const DESCRIPTION_LENGTH = 160;

const AVAILABILITY: Record<string, string> = {
  in_stock: "В наличии",
  out_of_stock: "Нет в наличии",
};

export async function generateMetadata({ params }: PageProps<"/p/[productId]">): Promise<Metadata> {
  const { productId } = await params;
  const product = await fetchCatalogProduct(productId);
  if (product === null) {
    return { title: "Товар не найден", robots: { index: false } };
  }
  // the first line of the description is what a search result shows
  const description =
    product.description?.slice(0, DESCRIPTION_LENGTH) ??
    `${product.name} в магазине ${product.store.display_name}`;
  const title = `${product.name} — ${product.store.display_name}`;
  const cover = product.images[0];

  return {
    title,
    description,
    // a product lives on the marketplace domain and nowhere else
    alternates: { canonical: productUrl(product.id) },
    openGraph: {
      type: "website",
      title,
      description,
      url: productUrl(product.id),
      images:
        cover === undefined
          ? undefined
          : [{ url: cover.image_url, alt: cover.alt_text ?? product.name }],
    },
  };
}

export default async function ProductPage({ params }: PageProps<"/p/[productId]">) {
  const { productId } = await params;
  const product = await fetchCatalogProduct(productId);
  // a product that is not public answers exactly as one that does not exist
  if (product === null) {
    notFound();
  }
  const cover = product.images[0];

  return (
    <>
      <SiteHeader />
      <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-8">
        <nav className="text-sm text-ink-muted">
          <Link href="/catalog" className="hover:text-brand">
            Каталог
          </Link>
          {" / "}
          <Link
            href={`/catalog?category=${encodeURIComponent(product.category.slug)}`}
            className="hover:text-brand"
          >
            {product.category.name}
          </Link>
        </nav>

        <div className="grid gap-8 md:grid-cols-2">
          <div className="flex flex-col gap-3">
            <div className="relative aspect-square overflow-hidden rounded-card bg-surface-muted">
              {cover === undefined ? (
                <span className="flex h-full items-center justify-center text-ink-muted">
                  Без фото
                </span>
              ) : (
                <Image
                  src={cover.image_url}
                  alt={cover.alt_text ?? product.name}
                  fill
                  sizes="(max-width: 768px) 100vw, 50vw"
                  className="object-cover"
                  priority
                />
              )}
            </div>
            {product.images.length > 1 ? (
              <div className="grid grid-cols-4 gap-2">
                {product.images.slice(1).map((image) => (
                  <div
                    key={image.image_url}
                    className="relative aspect-square overflow-hidden rounded-lg bg-surface-muted"
                  >
                    <Image
                      src={image.image_url}
                      alt={image.alt_text ?? product.name}
                      fill
                      sizes="20vw"
                      className="object-cover"
                    />
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="flex flex-col gap-4">
            <h1 className="text-3xl font-semibold tracking-tight">{product.name}</h1>
            <p className="text-3xl font-semibold">{formatPrice(product.price, product.currency)}</p>
            <p className="text-sm text-ink-muted">
              {AVAILABILITY[product.availability_status] ?? product.availability_status}
            </p>
            {product.description === null ? null : (
              <p className="whitespace-pre-line">{product.description}</p>
            )}
            <div className="mt-auto rounded-card border border-ink-muted/15 p-4">
              <p className="text-sm text-ink-muted">Продавец</p>
              <Link
                href={`/s/${encodeURIComponent(product.store.subdomain)}`}
                className="text-lg font-medium hover:text-brand"
              >
                {product.store.display_name}
              </Link>
              <p className="mt-2 text-sm text-ink-muted">
                Заказ обсуждается с продавцом напрямую — оплата на платформе появится позже.
              </p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
