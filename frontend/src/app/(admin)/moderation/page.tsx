import type { Metadata } from "next";
import Image from "next/image";

import { ModerationNav } from "@/components/moderation/ModerationNav";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import { getModerationBusinesses, getModerationProducts, requireRole } from "@/lib/dal";
import { formatPrice } from "@/lib/format";

export const metadata: Metadata = {
  title: "Модерация товаров",
  robots: { index: false, follow: false },
};

const VERDICTS: Verdict[] = [
  { label: "Одобрить", action: "approve" },
  {
    label: "Отклонить",
    action: "reject",
    reasonPrompt: "Что продавцу исправить? Текст увидит он, а не покупатель.",
    danger: true,
  },
];

export default async function ModerationProductsPage() {
  await requireRole("moderator", "admin");
  const [queue, businesses] = await Promise.all([
    getModerationProducts(),
    getModerationBusinesses(),
  ]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <ModerationNav
        current="products"
        products={queue?.total ?? 0}
        businesses={businesses?.total ?? 0}
      />

      {queue === null ? (
        <p className="text-danger">Очередь сейчас недоступна, попробуйте обновить страницу.</p>
      ) : queue.items.length === 0 ? (
        <p className="text-ink-muted">Очередь пуста — всё проверено.</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {queue.items.map((product) => {
            const cover = product.images[0];
            return (
              <li
                key={product.id}
                className="flex flex-col gap-4 rounded-card border border-ink-muted/20 p-4 sm:flex-row"
              >
                <div className="relative aspect-square w-full shrink-0 overflow-hidden rounded-lg bg-surface-muted sm:size-40">
                  {cover === undefined ? (
                    <span className="flex h-full items-center justify-center text-sm text-ink-muted">
                      Без фото
                    </span>
                  ) : (
                    <Image
                      src={cover.image_url}
                      alt={cover.alt_text ?? product.name}
                      fill
                      sizes="160px"
                      className="object-cover"
                    />
                  )}
                </div>

                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <h2 className="text-lg font-medium">{product.name}</h2>
                    <span className="text-lg font-semibold">
                      {formatPrice(product.price, product.currency)}
                    </span>
                  </div>
                  <p className="text-sm text-ink-muted">
                    {product.seller_name}
                    {product.subdomain === null
                      ? " — без витрины"
                      : ` · ${product.subdomain}`} · {product.category_name} · остаток{" "}
                    {product.stock_quantity}
                  </p>
                  {product.description === null ? (
                    <p className="text-sm text-ink-muted">Описания нет.</p>
                  ) : (
                    <p className="whitespace-pre-line text-sm">{product.description}</p>
                  )}
                  {product.images.length > 1 ? (
                    <p className="text-sm text-ink-muted">
                      Ещё фотографий: {product.images.length - 1}
                    </p>
                  ) : null}
                  <VerdictButtons
                    basePath={`/moderation/products/${product.id}`}
                    verdicts={VERDICTS}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
