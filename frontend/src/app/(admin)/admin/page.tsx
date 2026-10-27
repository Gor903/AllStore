import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { RoleSelect } from "@/components/admin/RoleSelect";
import { TransferAdmin } from "@/components/admin/TransferAdmin";
import { Pagination } from "@/components/catalog/Pagination";
import { AccountRows } from "@/components/moderation/AccountRows";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { ADMIN_PAGE_SIZE, getAdminUsers, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Пользователи",
  robots: { index: false, follow: false },
};

export default async function AdminUsersPage({ searchParams }: PageProps<"/admin">) {
  const user = await requireRole("admin");
  const params = toSearchParams(await searchParams);
  const { q, offset } = parseCatalogQuery(params);
  const page = await getAdminUsers(q ?? "", offset);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <AdminNav current="users" />
      <p className="text-sm text-ink-muted">
        Вы вошли как {user.email}. Администратор на площадке один: роль не снимают, её передают.
        Модератора назначают приглашением на вкладке рядом — смена роли здесь годится для аккаунта,
        который уже есть.
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
          <AccountRows
            items={page.items}
            viewerId={user.id}
            extra={(item) =>
              item.id === user.id ? null : (
                <div className="flex flex-wrap items-start gap-2">
                  <RoleSelect userId={item.id} role={item.role} />
                  {item.role === "moderator" ? (
                    <TransferAdmin userId={item.id} email={item.email} />
                  ) : null}
                </div>
              )
            }
          />
          <Pagination
            path="/admin"
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
