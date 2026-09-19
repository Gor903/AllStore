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
      <StatusBadge label="Backend" healthy={health !== null} />
    </main>
  );
}
