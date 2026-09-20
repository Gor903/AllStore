import Image from "next/image";
import Link from "next/link";

import type { CatalogProduct } from "@/lib/api";
import { formatPrice } from "@/lib/format";

type ProductCardProps = {
  product: CatalogProduct;
  /** Built by the page: on the marketplace it leaves for the shop's subdomain. */
  href: string;
};

export function ProductCard({ product, href }: ProductCardProps) {
  const cover = product.images[0];

  return (
    <Link
      href={href}
      className="group flex flex-col overflow-hidden rounded-card border border-ink-muted/15 transition hover:border-brand/60"
    >
      <div className="relative aspect-square bg-surface-muted">
        {cover === undefined ? (
          <span className="flex h-full items-center justify-center text-sm text-ink-muted">
            Без фото
          </span>
        ) : (
          <Image
            src={cover.image_url}
            alt={cover.alt_text ?? product.name}
            fill
            sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
            className="object-cover"
          />
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <h3 className="line-clamp-2 font-medium group-hover:text-brand">{product.name}</h3>
        <span className="mt-auto pt-2 text-lg font-semibold">
          {formatPrice(product.price, product.currency)}
        </span>
        <span className="text-sm text-ink-muted">{product.store.display_name}</span>
      </div>
    </Link>
  );
}
