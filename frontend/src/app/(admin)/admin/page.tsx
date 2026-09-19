import type { Metadata } from "next";

import { LogoutButton } from "@/components/auth/LogoutButton";
import { requireRole } from "@/lib/dal";

export const metadata: Metadata = {
  title: "Админка",
  robots: { index: false, follow: false },
};

export default async function AdminPage() {
  const user = await requireRole("admin");

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Админка</h1>
        <LogoutButton />
      </header>
      <p className="text-sm text-ink-muted">Вы вошли как {user.email}.</p>
      <p className="text-sm text-ink-muted">Модерация товаров появится на этапе 5.</p>
    </main>
  );
}
