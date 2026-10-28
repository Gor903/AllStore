import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminNav } from "@/components/admin/AdminNav";
import { RoleSelect } from "@/components/admin/RoleSelect";
import { TransferAdmin } from "@/components/admin/TransferAdmin";
import { AccountRows } from "@/components/moderation/AccountRows";
import { getAdminUser, requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Аккаунт",
  robots: { index: false, follow: false },
};

const ROLE: Record<string, string> = {
  buyer: "покупатель",
  seller: "продавец",
  moderator: "модератор",
  admin: "администратор",
};

function when(value: string | null): string {
  return value === null ? "никогда" : new Date(value).toLocaleString("ru-RU");
}

export default async function AdminUserPage({ params }: PageProps<"/admin/users/[userId]">) {
  const viewer = await requireRole("admin");
  const { userId } = await params;
  const account = await getAdminUser(userId);
  if (account === null) {
    notFound();
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-10">
      <AdminNav current="users" />
      <nav className="text-sm text-ink-muted">
        <Link href="/admin" className="hover:text-brand">
          Пользователи
        </Link>
        {" / аккаунт"}
      </nav>

      <h2 className="text-xl font-semibold">{account.email}</h2>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        <dt className="text-ink-muted">Роль</dt>
        <dd>{ROLE[account.role] ?? account.role}</dd>
        <dt className="text-ink-muted">Телефон</dt>
        <dd>{account.phone ?? "не указан"}</dd>
        <dt className="text-ink-muted">Зарегистрирован</dt>
        <dd>{when(account.created_at)}</dd>
        <dt className="text-ink-muted">Последний вход</dt>
        <dd>{when(account.last_login_at)}</dd>
        <dt className="text-ink-muted">Почта подтверждена</dt>
        <dd>{when(account.email_verified_at)}</dd>
      </dl>

      {/* the same row everybody else gets: barring is one action in the matrix, and it must
        not look or behave differently because this screen is about one person */}
      <AccountRows
        items={[account]}
        viewerId={viewer.id}
        extra={(item) =>
          item.id === viewer.id ? null : (
            <div className="flex flex-wrap items-start gap-2">
              <RoleSelect userId={item.id} role={item.role} />
              {item.role === "moderator" ? (
                <TransferAdmin userId={item.id} email={item.email} />
              ) : null}
            </div>
          )
        }
      />
    </main>
  );
}
