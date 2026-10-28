import type { Metadata } from "next";

import { AccountRows } from "@/components/moderation/AccountRows";
import { ModerationNav } from "@/components/moderation/ModerationNav";
import { Pagination } from "@/components/catalog/Pagination";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import {
  ADMIN_PAGE_SIZE,
  getModerationBusinesses,
  getModerationProducts,
  getReachableAccounts,
  requireRole,
} from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Аккаунты",
  robots: { index: false, follow: false },
};

export default async function ModerationAccountsPage({
  searchParams,
}: PageProps<"/moderation/accounts">) {
  const viewer = await requireRole("moderator", "admin");
  const params = toSearchParams(await searchParams);
  const { q, offset } = parseCatalogQuery(params);
  const [page, queue, businesses] = await Promise.all([
    getReachableAccounts(q ?? "", offset),
    getModerationProducts(),
    getModerationBusinesses(),
  ]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <ModerationNav
        current="accounts"
        isAdmin={viewer.role === "admin"}
        products={queue?.total ?? 0}
        businesses={businesses?.total ?? 0}
      />
      <p className="text-sm text-ink-muted">
        Здесь только те, кого вы можете заблокировать: модератор видит покупателей и продавцов,
        администратор — ещё и модераторов. Блокировка требует причины, снимается отдельным действием
        и остаётся в истории. Магазин заблокированного продавца гаснет сам.
      </p>

      <form method="get" className="flex flex-wrap gap-2">
        <label className="sr-only" htmlFor="q">
          Поиск по email
        </label>
        <input
          id="q"
          name="q"
          defaultValue={q ?? ""}
          placeholder="Часть адреса почты"
          className="min-w-64 flex-1 rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
        />
        <button type="submit" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
          Найти
        </button>
      </form>

      {page === null ? (
        <p className="text-danger">Список сейчас недоступен, попробуйте обновить страницу.</p>
      ) : page.items.length === 0 ? (
        <p className="text-ink-muted">Никого не нашлось.</p>
      ) : (
        <>
          <AccountRows items={page.items} viewerId={viewer.id} />
          <Pagination
            path="/moderation/accounts"
            params={q === null ? new URLSearchParams() : new URLSearchParams({ q })}
            offset={offset}
            pageSize={ADMIN_PAGE_SIZE}
            total={page.total}
          />
        </>
      )}
    </main>
  );
}
