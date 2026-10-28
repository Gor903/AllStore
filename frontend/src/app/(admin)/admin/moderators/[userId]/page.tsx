import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminNav } from "@/components/admin/AdminNav";
import { AccountRows } from "@/components/moderation/AccountRows";
import { getAuditLogs, getModeratorRecord, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Модератор",
  robots: { index: false, follow: false },
};

const COUNTS = [
  { key: "products_approved", label: "Товаров одобрено" },
  { key: "products_rejected", label: "Товаров отклонено" },
  { key: "businesses_approved", label: "Продавцов допущено" },
  { key: "businesses_refused", label: "Заявок отклонено" },
  { key: "accounts_blocked", label: "Аккаунтов заблокировано" },
] as const;

export default async function ModeratorPage({ params }: PageProps<"/admin/moderators/[userId]">) {
  const viewer = await requireRole("admin");
  const { userId } = await params;
  const record = await getModeratorRecord(userId);
  if (record === null) {
    notFound();
  }
  // their own entries, newest first: the counts say how much, the feed says what exactly
  const journal = await getAuditLogs(0, { actorId: userId });

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <AdminNav current="moderators" />
      <nav className="text-sm text-ink-muted">
        <Link href="/admin/moderators" className="hover:text-brand">
          Модераторы
        </Link>
        {" / карточка"}
      </nav>

      <h2 className="text-xl font-semibold">{record.moderator.email}</h2>
      <p className="text-sm text-ink-muted">
        Цифры посчитаны по самим решениям, а не по счётчику рядом с ними: счётчик, который ведут
        отдельно, может разойтись с правдой, а здесь он читался бы как доказательство.
      </p>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {COUNTS.map((item) => (
          <div key={item.key} className="rounded-card border border-ink-muted/20 p-4">
            <dt className="text-sm text-ink-muted">{item.label}</dt>
            <dd className="text-2xl font-semibold">{record[item.key]}</dd>
          </div>
        ))}
      </dl>

      <AccountRows items={[record.moderator]} viewerId={viewer.id} />

      <section className="flex flex-col gap-2">
        <h3 className="font-medium">Последние действия</h3>
        {journal === null ? (
          <p className="text-danger">Журнал сейчас недоступен.</p>
        ) : journal.items.length === 0 ? (
          <p className="text-ink-muted">Пока ничего не делал.</p>
        ) : (
          <>
            <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
              {journal.items.map((entry) => (
                <li key={entry.id} className="flex flex-col gap-1 p-4 text-sm">
                  <span>{entry.action}</span>
                  <span className="text-xs text-ink-muted">
                    {new Date(entry.created_at).toLocaleString("ru-RU")} · {entry.entity_type}
                  </span>
                </li>
              ))}
            </ul>
            <Link
              href={`/admin/audit?actor_id=${encodeURIComponent(userId)}`}
              className="text-sm text-brand"
            >
              Все записи этого модератора в журнале ({journal.total})
            </Link>
          </>
        )}
      </section>
    </main>
  );
}
