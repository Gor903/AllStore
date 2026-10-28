import type { Metadata } from "next";
import Image from "next/image";

import { ModerationNav } from "@/components/moderation/ModerationNav";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import { Pagination } from "@/components/catalog/Pagination";
import { formatPrice } from "@/lib/format";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import {
  ADMIN_PAGE_SIZE,
  getModerationBusinesses,
  getModerationProducts,
  requireRole,
  searchModerationCatalog,
} from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Поиск по каталогу",
  robots: { index: false, follow: false },
};

const HIDE: Verdict[] = [
  {
    label: "Снять с полки",
    action: "hide",
    reasonPrompt: "Почему товар снимается? Текст останется в истории модерации.",
    danger: true,
  },
];

const PUBLISH: Verdict[] = [{ label: "Вернуть на полку", action: "publish" }];

/** What may be done to a product that is not in the queue: it has a verdict already. */
function verdictsFor(publication: string): Verdict[] | null {
  if (publication === "published") {
    return HIDE;
  }
  return publication === "hidden" ? PUBLISH : null;
}

export default async function ModerationCatalogPage({
  searchParams,
}: PageProps<"/moderation/catalog">) {
  const viewer = await requireRole("moderator", "admin");
  const { q, offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const query = q ?? "";
  const [found, queue, businesses] = await Promise.all([
    searchModerationCatalog(query, offset),
    getModerationProducts(),
    getModerationBusinesses(),
  ]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <ModerationNav
        current="catalog"
        isAdmin={viewer.role === "admin"}
        products={queue?.total ?? 0}
        businesses={businesses?.total ?? 0}
      />

      <form method="get" className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="q">
          Поиск по каталогу
        </label>
        <input
          id="q"
          name="q"
          defaultValue={query}
          placeholder="Название товара или магазина"
          className="min-w-64 flex-1 rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
        />
        <button type="submit" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
          Найти
        </button>
      </form>
      <p className="text-sm text-ink-muted">
        Очередь держит только то, что ждёт проверки. Здесь ищется товар в любом состоянии — тот, на
        который пожаловались уже после публикации.
      </p>

      {found === null ? (
        <p className="text-danger">Поиск сейчас недоступен, попробуйте обновить страницу.</p>
      ) : query === "" ? null : found.items.length === 0 ? (
        <p className="text-ink-muted">Ничего не нашлось.</p>
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
            {found.items.map((product) => {
              const cover = product.images[0];
              const verdicts = verdictsFor(product.publication_status);
              return (
                <li key={product.id} className="flex flex-wrap gap-4 p-4">
                  <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-surface-muted">
                    {cover === undefined ? null : (
                      <Image
                        src={cover.image_url}
                        alt={cover.alt_text ?? product.name}
                        fill
                        sizes="80px"
                        unoptimized
                        className="object-cover"
                      />
                    )}
                  </div>
                  <div className="min-w-48 flex-1">
                    <p className="font-medium">{product.name}</p>
                    <p className="text-sm text-ink-muted">
                      {product.seller_name} · {product.category_name} ·{" "}
                      {formatPrice(product.price, product.currency)}
                    </p>
                    <p className="text-sm text-ink-muted">
                      проверка: {product.moderation_status} · полка: {product.publication_status}
                    </p>
                  </div>
                  {verdicts === null ? (
                    <p className="self-center text-sm text-ink-muted">
                      Решение принимается в очереди
                    </p>
                  ) : (
                    <VerdictButtons
                      basePath={`/moderation/products/${product.id}`}
                      verdicts={verdicts}
                    />
                  )}
                </li>
              );
            })}
          </ul>
          <Pagination
            path="/moderation/catalog"
            params={new URLSearchParams({ q: query })}
            offset={offset}
            pageSize={ADMIN_PAGE_SIZE}
            total={found.total}
          />
        </>
      )}
    </main>
  );
}
