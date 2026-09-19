import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Админка",
  robots: { index: false, follow: false },
};

export default function AdminPage() {
  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-2xl font-semibold">Админка</h1>
      <p className="mt-2 text-ink-muted">Модерация и управление платформой — этап 5.</p>
    </main>
  );
}
