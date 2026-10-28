import type { Metadata } from "next";
import Image from "next/image";

import { Pagination } from "@/components/catalog/Pagination";
import { ModerationNav } from "@/components/moderation/ModerationNav";
import { VerdictButtons, type Verdict } from "@/components/moderation/VerdictButtons";
import type { ReportedSubject } from "@/lib/api";
import { parseCatalogQuery, toSearchParams } from "@/lib/catalog-query";
import {
  ADMIN_PAGE_SIZE,
  getModerationBusinesses,
  getModerationProducts,
  getReportQueue,
  requireRole,
} from "@/lib/dal";
import { formatPrice } from "@/lib/format";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Жалобы",
  robots: { index: false, follow: false },
};

function verdictsFor(subject: ReportedSubject): Verdict[] {
  const thing = subject.product === null ? "магазин" : "товар";
  return [
    {
      label: subject.product === null ? "Приостановить магазин" : "Снять товар с полки",
      action: "uphold",
      reasonPrompt: `Что подтвердилось? Продавец прочтёт это в истории модерации.`,
      danger: true,
    },
    {
      label: "Отклонить жалобу",
      action: "dismiss",
      // nothing happens to the subject, so the reason is the only record of the decision
      reasonPrompt: `Почему ${thing} остаётся как есть? Текст останется в жалобе.`,
    },
  ];
}

/** Where a complaint is sent: the identifier the resolution routes are addressed by. */
function basePathOf(subject: ReportedSubject): string {
  return subject.product === null
    ? `/moderation/reports/business/${subject.business_id}`
    : `/moderation/reports/product/${subject.product.id}`;
}

export default async function ReportsPage({ searchParams }: PageProps<"/moderation/reports">) {
  const viewer = await requireRole("moderator", "admin");
  const { offset } = parseCatalogQuery(toSearchParams(await searchParams));
  const [queue, products, businesses] = await Promise.all([
    getReportQueue(offset),
    getModerationProducts(),
    getModerationBusinesses(),
  ]);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 px-6 py-10">
      <ModerationNav
        current="reports"
        isAdmin={viewer.role === "admin"}
        products={products?.total ?? 0}
        businesses={businesses?.total ?? 0}
        reports={queue?.total ?? 0}
      />
      <p className="text-sm text-ink-muted">
        Одна строка — один предмет, даже если на него пожаловались десять раз. Решение закрывает все
        жалобы на него сразу.
      </p>

      {queue === null ? (
        <p className="text-danger">Очередь сейчас недоступна, попробуйте обновить страницу.</p>
      ) : queue.items.length === 0 ? (
        <p className="text-ink-muted">Жалоб нет.</p>
      ) : (
        <>
          <ul className="flex flex-col divide-y divide-ink-muted/15 rounded-card border border-ink-muted/20">
            {queue.items.map((subject) => {
              const cover = subject.product?.images[0];
              return (
                <li
                  key={subject.product?.id ?? subject.business_id}
                  className="flex flex-wrap gap-4 p-4"
                >
                  <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-lg bg-surface-muted">
                    {cover === undefined ? null : (
                      <Image
                        src={cover.image_url}
                        alt={cover.alt_text ?? ""}
                        fill
                        sizes="80px"
                        unoptimized
                        className="object-cover"
                      />
                    )}
                  </div>

                  <div className="min-w-56 flex-1">
                    {subject.product === null ? (
                      <>
                        <p className="font-medium">Магазин: {subject.shop?.display_name}</p>
                        <p className="text-sm text-ink-muted">{subject.shop?.subdomain}</p>
                      </>
                    ) : (
                      <>
                        <p className="font-medium">{subject.product.name}</p>
                        <p className="text-sm text-ink-muted">
                          {subject.product.seller_name} · {subject.product.category_name} ·{" "}
                          {formatPrice(subject.product.price, subject.product.currency)}
                        </p>
                      </>
                    )}
                    <p className="mt-1 text-sm">
                      Жалоб: <span className="font-medium">{subject.total}</span>
                    </p>
                    <ul className="mt-1 flex flex-col gap-1 text-sm text-ink-muted">
                      {subject.reasons.map((reason, index) => (
                        <li key={`${subject.product?.id ?? subject.business_id}-${index}`}>
                          «{reason}»
                        </li>
                      ))}
                    </ul>
                  </div>

                  <VerdictButtons basePath={basePathOf(subject)} verdicts={verdictsFor(subject)} />
                </li>
              );
            })}
          </ul>
          <Pagination
            path="/moderation/reports"
            params={new URLSearchParams()}
            offset={offset}
            pageSize={ADMIN_PAGE_SIZE}
            total={queue.total}
          />
        </>
      )}
    </main>
  );
}
