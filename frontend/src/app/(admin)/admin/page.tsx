import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { RoleSelect } from "@/components/admin/RoleSelect";
import { Pagination } from "@/components/catalog/Pagination";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import { ADMIN_PAGE_SIZE, getAdminUsers, requireRole } from "@/lib/dal";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Пользователи",
  robots: { index: false, follow: false },
};

const STATUS: Record<string, string> = {
  active: "активен",
  suspended: "приостановлен",
  blocked: "заблокирован",
};

const BLOCK: Verdict[] = [
  {
    label: "Заблокировать",
    action: "block",
    reasonPrompt: "За что? Причина останется в журнале.",
    danger: true,
  },
];

const UNBLOCK: Verdict[] = [{ label: "Разблокировать", action: "unblock" }];

export default async function AdminUsersPage({ searchParams }: PageProps<"/admin">) {
  const user = await requireRole("admin");
  const params = toSearchParams(await searchParams);
  const { q, offset } = parseCatalogQuery(params);
  const page = await getAdminUsers(q ?? "", offset);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <AdminNav current="users" />
      <p className="text-sm text-ink-muted">Вы вошли как {user.email}.</p>

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
          <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
            {page.items.map((item) => (
              <li key={item.id} className="flex flex-wrap items-start gap-4 p-4">
                <div className="min-w-48 flex-1">
                  <p className="font-medium">{item.email}</p>
                  <p className="text-sm text-ink-muted">
                    {STATUS[item.status] ?? item.status}
                    {item.id === user.id ? " — это вы" : ""}
                  </p>
                </div>
                <RoleSelect userId={item.id} role={item.role} />
                {/* /accounts, not /admin: barring is a moderator's action too, so it is one
                    route with one rule rather than one per panel */}
                <VerdictButtons
                  basePath={`/accounts/${item.id}`}
                  verdicts={item.status === "blocked" ? UNBLOCK : BLOCK}
                />
              </li>
            ))}
          </ul>
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
