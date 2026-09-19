import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Кабинет продавца",
  robots: { index: false, follow: false },
};

export default function DashboardPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-2xl font-semibold">Кабинет продавца</h1>
      <p className="mt-2 text-ink-muted">Авторизация и управление магазином — этапы 2–4.</p>
    </main>
  );
}
