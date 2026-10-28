import type { Metadata } from "next";
import Link from "next/link";

import { AdminNav } from "@/components/admin/AdminNav";
import { AppointModerator } from "@/components/admin/AppointModerator";
import { ResetModeratorPassword } from "@/components/admin/ResetModeratorPassword";
import { Pagination } from "@/components/catalog/Pagination";
import { AccountRows } from "@/components/moderation/AccountRows";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { ADMIN_PAGE_SIZE, getModerators, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Модераторы",
  robots: { index: false, follow: false },
};

export default async function ModeratorsPage({ searchParams }: PageProps<"/admin/moderators">) {
  const viewer = await requireRole("admin");
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const page = await getModerators("", offset);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <AdminNav current="moderators" />
      <p className="text-sm text-ink-muted">
        Модератор судит чужие магазины и закрывает чужие аккаунты, поэтому роль не берут на сайте —
        её выдаёт администратор, заводя аккаунт сам.
      </p>

      <AppointModerator />

      <section className="flex flex-col gap-3">
        <h2 className="font-medium">Действующие модераторы</h2>
        {/* not on the accounts screen: that one is about the people the platform serves */}
        {page === null ? (
          <p className="text-danger">Список сейчас недоступен, попробуйте обновить страницу.</p>
        ) : page.items.length === 0 ? (
          <p className="text-ink-muted">Модераторов пока нет — заведите первого.</p>
        ) : (
          <>
            <AccountRows
              items={page.items}
              viewerId={viewer.id}
              extra={(item) => (
                <div className="flex flex-wrap items-start gap-2">
                  <Link
                    href={`/admin/moderators/${item.id}`}
                    className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium"
                  >
                    Что решил
                  </Link>
                  <ResetModeratorPassword userId={item.id} email={item.email} />
                </div>
              )}
            />
            <Pagination
              path="/admin/moderators"
              params={new URLSearchParams()}
              offset={offset}
              pageSize={ADMIN_PAGE_SIZE}
              total={page.total}
            />
          </>
        )}
      </section>
    </main>
  );
}
