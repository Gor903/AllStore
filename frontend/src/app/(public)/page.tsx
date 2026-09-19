import Link from "next/link";

import { StatusBadge } from "@/components/StatusBadge";
import { fetchBackendHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const health = await fetchBackendHealth();

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6">
      <h1 className="text-4xl font-semibold tracking-tight">AllStore.am</h1>
      <p className="text-ink-muted">
        Каркас платформы поднят. Каталог, магазины и кабинет продавца появятся на следующих этапах.
      </p>
      <div className="flex gap-3">
        <Link href="/register" className="rounded-lg bg-brand px-4 py-2 font-medium text-white">
          Зарегистрироваться
        </Link>
        <Link href="/login" className="rounded-lg border border-ink-muted/30 px-4 py-2 font-medium">
          Войти
        </Link>
      </div>
      <StatusBadge label="Backend" healthy={health !== null} />
    </main>
  );
}
