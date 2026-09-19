import type { Metadata } from "next";

import { LogoutButton } from "@/components/auth/LogoutButton";
import { getMyBusiness, requireUser } from "@/lib/dal";

export const metadata: Metadata = {
  title: "Кабинет",
  robots: { index: false, follow: false },
};

const BUSINESS_STATUS: Record<string, string> = {
  pending: "на проверке модератором",
  active: "активен",
  suspended: "приостановлен",
  blocked: "заблокирован",
};

export default async function DashboardPage() {
  // the real check lives here, not in the layout: layouts do not re-render on navigation
  const user = await requireUser();
  const business = user.role === "seller" ? await getMyBusiness() : null;

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-16">
      <header className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold">Кабинет</h1>
        <LogoutButton />
      </header>

      <dl className="grid gap-2 text-sm">
        <div className="flex gap-2">
          <dt className="text-ink-muted">Email:</dt>
          <dd>{user.email}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-ink-muted">Роль:</dt>
          <dd>{user.role}</dd>
        </div>
      </dl>

      {business ? (
        <section className="rounded-card border border-ink-muted/20 p-4">
          <h2 className="font-medium">{business.display_name}</h2>
          <p className="mt-1 text-sm text-ink-muted">
            {business.legal_name} — {BUSINESS_STATUS[business.status] ?? business.status}
          </p>
        </section>
      ) : null}

      <p className="text-sm text-ink-muted">
        Товары и настройки магазина появятся на следующих этапах.
      </p>
    </main>
  );
}
