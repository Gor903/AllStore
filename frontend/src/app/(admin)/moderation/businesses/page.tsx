import type { Metadata } from "next";

import { ModerationNav } from "@/components/moderation/ModerationNav";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import { getModerationBusinesses, getModerationProducts, requireRole } from "@/lib/dal";
import { env } from "@/lib/env";

export const metadata: Metadata = {
  title: "Модерация продавцов",
  robots: { index: false, follow: false },
};

const VERDICTS: Verdict[] = [
  { label: "Допустить", action: "approve" },
  {
    label: "Отклонить",
    action: "reject",
    reasonPrompt: "Что продавцу исправить? Он прочитает это в кабинете и подаст заявку снова.",
    danger: true,
  },
  {
    label: "Заблокировать",
    action: "block",
    reasonPrompt: "Почему продавец не допускается совсем? Причина останется в истории решений.",
    danger: true,
  },
];

const DECISION: Record<string, string> = {
  approved: "допущен",
  rejected: "отклонён",
  resubmitted: "подал заявку снова",
  suspended: "приостановлен",
  blocked: "заблокирован",
  restored: "восстановлен",
};

export default async function ModerationBusinessesPage() {
  await requireRole("moderator", "admin");
  const [businesses, queue] = await Promise.all([
    getModerationBusinesses(),
    getModerationProducts(),
  ]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <ModerationNav
        current="businesses"
        products={queue?.total ?? 0}
        businesses={businesses?.total ?? 0}
      />

      <p className="text-sm text-ink-muted">
        Пока продавец не допущен, его магазин никому не виден, а товары не публикуются, даже если
        одобрены по отдельности. Отклонение — не бан: продавец прочитает причину, исправит и подаст
        заявку снова. Блокировка закрывает дорогу совсем.
      </p>

      {businesses === null ? (
        <p className="text-danger">Очередь сейчас недоступна, попробуйте обновить страницу.</p>
      ) : businesses.items.length === 0 ? (
        <p className="text-ink-muted">Заявок нет — все продавцы рассмотрены.</p>
      ) : (
        <ul className="flex flex-col gap-4">
          {businesses.items.map((business) => (
            <li
              key={business.id}
              className="flex flex-col gap-2 rounded-card border border-ink-muted/20 p-4"
            >
              <h2 className="text-lg font-medium">{business.display_name}</h2>
              <p className="text-sm text-ink-muted">{business.legal_name}</p>
              {business.description === null ? null : (
                <p className="text-sm">{business.description}</p>
              )}
              <p className="text-sm text-ink-muted">
                {business.subdomain === null
                  ? "Витрину ещё не создал"
                  : `Адрес: ${business.subdomain}.${env.baseDomain}`}
              </p>
              {business.history.length === 0 ? null : (
                <details className="text-sm">
                  <summary className="cursor-pointer text-ink-muted">
                    Эту заявку уже смотрели ({business.history.length})
                  </summary>
                  <ul className="mt-2 flex flex-col gap-1">
                    {business.history.map((entry) => (
                      <li key={entry.created_at} className="text-ink-muted">
                        {new Date(entry.created_at).toLocaleString("ru-RU")} —{" "}
                        {DECISION[entry.decision] ?? entry.decision}
                        {entry.reason === null ? "" : `: ${entry.reason}`}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
              <VerdictButtons
                basePath={`/moderation/businesses/${business.id}`}
                verdicts={VERDICTS}
              />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
