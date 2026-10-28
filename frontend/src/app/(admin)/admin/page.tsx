import type { Metadata } from "next";
import Link from "next/link";

import { AccountFilters } from "@/components/admin/AccountFilters";
import { AdminNav } from "@/components/admin/AdminNav";
import { RoleSelect } from "@/components/admin/RoleSelect";
import { TransferAdmin } from "@/components/admin/TransferAdmin";
import { Pagination } from "@/components/catalog/Pagination";
import { AccountRows } from "@/components/moderation/AccountRows";
import { accountSearchParams, parseAccountQuery } from "@/lib/account-query";
import { toSearchParams } from "@/lib/catalog-query";
import { ADMIN_PAGE_SIZE, getAdminUsers, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Пользователи",
  robots: { index: false, follow: false },
};

export default async function AdminUsersPage({ searchParams }: PageProps<"/admin">) {
  const user = await requireRole("admin");
  const query = parseAccountQuery(toSearchParams(await searchParams));
  const page = await getAdminUsers(query);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <AdminNav current="users" />
      <p className="text-sm text-ink-muted">
        Вы вошли как {user.email}. Администратор на площадке один: роль не снимают, её передают.
        Модератора назначают приглашением на вкладке рядом — смена роли здесь годится для аккаунта,
        который уже есть.
      </p>

      <AccountFilters query={query} />

      {page === null ? (
        <p className="text-danger">Список сейчас недоступен, попробуйте обновить страницу.</p>
      ) : page.items.length === 0 ? (
        <p className="text-ink-muted">Никого не нашлось.</p>
      ) : (
        <>
          <p className="text-sm text-ink-muted">Найдено: {page.total}</p>
          <AccountRows
            items={page.items}
            viewerId={user.id}
            extra={(item) =>
              item.id === user.id ? null : (
                <div className="flex flex-wrap items-start gap-2">
                  <Link
                    href={`/admin/users/${item.id}`}
                    className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium"
                  >
                    Карточка
                  </Link>
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
            params={accountSearchParams(query)}
            offset={query.offset}
            pageSize={ADMIN_PAGE_SIZE}
            total={page.total}
          />
        </>
      )}
    </main>
  );
}
