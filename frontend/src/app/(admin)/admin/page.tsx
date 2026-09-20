import type { Metadata } from "next";
import Link from "next/link";

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
      <Link
        href="/moderation"
        className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white"
      >
        Очередь модерации
      </Link>
      <p className="text-sm text-ink-muted">
        Управление пользователями и категориями появится позже.
      </p>
    </main>
  );
}
