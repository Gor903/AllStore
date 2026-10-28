import type { Metadata } from "next";

import { AdminNav } from "@/components/admin/AdminNav";
import { requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Акции",
  robots: { index: false, follow: false },
};

/**
 * A route and a locked door, nothing more.
 *
 * What belongs here has not been decided — a discount on what, a promo code or not, who sees
 * it before it starts — and guessing would mean building something to be thrown away. The
 * page exists so the question has a place to land rather than to pretend at an answer.
 */
export default async function PromotionsPage() {
  await requireRole("admin");

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <AdminNav current="promotions" />
      <h2 className="text-xl font-semibold">Акции и скидки</h2>
      <p className="text-sm text-ink-muted">
        Раздел пока пуст. Что в нём будет — скидка на товар, на категорию или на магазин, промокоды,
        срок действия, кто видит акцию до её начала — ещё не описано, и угадывать здесь значило бы
        построить то, что придётся выбросить.
      </p>
      <p className="text-sm text-ink-muted">
        Права уже на месте: раздел видит только администратор.
      </p>
    </main>
  );
}
