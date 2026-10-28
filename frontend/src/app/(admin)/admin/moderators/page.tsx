import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { InviteModerator } from "@/components/admin/InviteModerator";
import { AccountRows } from "@/components/moderation/AccountRows";
import { Pagination } from "@/components/catalog/Pagination";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import { ADMIN_PAGE_SIZE, getModeratorInvitations, getModerators, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Модераторы",
  robots: { index: false, follow: false },
};

const STATUS: Record<string, string> = {
  pending: "действует",
  accepted: "принято",
  revoked: "отозвано",
  expired: "истекло",
};

const REVOKE: Verdict[] = [{ label: "Отозвать", action: "revoke", danger: true }];

export default async function ModeratorsPage({ searchParams }: PageProps<"/admin/moderators">) {
  const viewer = await requireRole("admin");
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const [page, moderators] = await Promise.all([
    getModeratorInvitations(offset),
    getModerators("", 0),
  ]);

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-6 py-10">
      <AdminNav current="moderators" />
      <p className="text-sm text-ink-muted">
        Модератором становятся только по персональному приглашению: роль судит чужие магазины,
        поэтому её выдают по имени, а не берут на сайте. Ссылка работает один раз и только для того
        адреса, на который выписана.
      </p>

      <section className="flex flex-col gap-3">
        <h2 className="font-medium">Действующие модераторы</h2>
        {/* not on the accounts screen: that one is about the people the platform serves */}
        {moderators === null ? (
          <p className="text-danger">Список сейчас недоступен, попробуйте обновить страницу.</p>
        ) : moderators.items.length === 0 ? (
          <p className="text-ink-muted">Модераторов пока нет — пригласите первого.</p>
        ) : (
          <AccountRows items={moderators.items} viewerId={viewer.id} />
        )}
      </section>

      <h2 className="font-medium">Приглашения</h2>
      <InviteModerator />

      {page === null ? (
        <p className="text-danger">Список сейчас недоступен, попробуйте обновить страницу.</p>
      ) : page.items.length === 0 ? (
        <p className="text-ink-muted">Приглашений пока не было.</p>
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
            {page.items.map((item) => (
              <li key={item.id} className="flex flex-wrap items-start gap-4 p-4">
                <div className="min-w-48 flex-1">
                  <p className="font-medium">{item.email}</p>
                  <p className="text-sm text-ink-muted">
                    {STATUS[item.status] ?? item.status} · выдал{" "}
                    {item.created_by_email ?? "аккаунт удалён"}
                  </p>
                  <p className="text-xs text-ink-muted">
                    {item.status === "pending"
                      ? `действует до ${new Date(item.expires_at).toLocaleString("ru-RU")}`
                      : `${new Date(
                          item.used_at ?? item.revoked_at ?? item.expires_at,
                        ).toLocaleString("ru-RU")}`}
                  </p>
                </div>
                {item.status === "pending" ? (
                  <VerdictButtons
                    basePath={`/admin/moderator-invitations/${item.id}`}
                    verdicts={REVOKE}
                  />
                ) : null}
              </li>
            ))}
          </ul>
          <Pagination
            path="/admin/moderators"
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
