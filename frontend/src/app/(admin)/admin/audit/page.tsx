import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { Pagination } from "@/components/catalog/Pagination";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { ADMIN_PAGE_SIZE, getAuditLogs, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Журнал действий",
  robots: { index: false, follow: false },
};

/** Every action the backend writes down, in the words an administrator reads it in. */
const ACTION: Record<string, string> = {
  "user.role_changed": "сменил роль",
  "user.admin_transferred": "передал администрирование",
  "user.blocked": "заблокировал",
  "user.unblocked": "разблокировал",
  "moderator.invited": "пригласил модератора",
  "moderator.invite_revoked": "отозвал приглашение",
  "moderator.invite_accepted": "принял приглашение модератора",
  "business.approved": "допустил продавца",
  "business.rejected": "отклонил заявку продавца",
  "business.resubmitted": "подал заявку снова",
  "business.suspended": "приостановил магазин",
  "business.blocked": "заблокировал магазин",
  "business.restored": "восстановил магазин",
  "product.approved": "одобрил товар",
  "product.rejected": "отклонил товар",
  "product.hidden": "снял товар с публикации",
  "product.published": "вернул товар в каталог",
  "store.customer_blocked": "закрыл магазин покупателю",
  "store.customer_unblocked": "вернул покупателю доступ в магазин",
  "report.upheld": "признал жалобу обоснованной",
  "report.dismissed": "отклонил жалобу",
  "category.created": "завёл категорию",
  "category.renamed": "переименовал категорию",
  "category.hidden": "скрыл категорию",
  "category.shown": "вернул категорию",
};

const DETAIL: Record<string, string> = {
  from: "было",
  to: "стало",
  reason: "причина",
  name: "название",
  slug: "адрес",
  email: "адрес",
  buyer: "покупатель",
  subject: "предмет",
  closed: "закрыто жалоб",
};

function described(details: Record<string, unknown>): string {
  return Object.entries(details)
    .map(([key, value]) => `${DETAIL[key] ?? key}: ${String(value)}`)
    .join(", ");
}

export default async function AuditLogPage({ searchParams }: PageProps<"/admin/audit">) {
  await requireRole("admin");
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const page = await getAuditLogs(offset);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <AdminNav current="audit" />
      <p className="text-sm text-ink-muted">
        Кто, что и когда — включая решения модераторов. Записи не редактируются и не удаляются: в
        этом их смысл, и кнопки, которая бы их убрала, здесь нет ни у кого.
      </p>

      {page === null ? (
        <p className="text-danger">Журнал сейчас недоступен, попробуйте обновить страницу.</p>
      ) : page.items.length === 0 ? (
        <p className="text-ink-muted">Пока ничего не происходило.</p>
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
            {page.items.map((entry) => (
              <li key={entry.id} className="flex flex-col gap-1 p-4">
                <p className="text-sm">
                  <span className="font-medium">{entry.actor_email ?? "аккаунт удалён"}</span>{" "}
                  {ACTION[entry.action] ?? entry.action}
                </p>
                {Object.keys(entry.details).length === 0 ? null : (
                  <p className="text-sm text-ink-muted">{described(entry.details)}</p>
                )}
                <p className="text-xs text-ink-muted">
                  {new Date(entry.created_at).toLocaleString("ru-RU")} · {entry.entity_type}{" "}
                  {entry.entity_id ?? ""}
                </p>
              </li>
            ))}
          </ul>
          <Pagination
            path="/admin/audit"
            params={new URLSearchParams()}
            offset={offset}
            pageSize={ADMIN_PAGE_SIZE}
            total={page.total}
          />
        </>
      )}
    </main>
  );
}
