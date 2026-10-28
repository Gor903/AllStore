import type { Metadata } from "next";
import Link from "next/link";

import { AdminNav } from "@/components/admin/AdminNav";
import { EmailChangeForm } from "@/components/admin/EmailChangeForm";
import { PasswordChangeForm } from "@/components/auth/PasswordChangeForm";
import { requireRole } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Доступ",
  robots: { index: false, follow: false },
};

export default async function AdminSecurityPage() {
  const user = await requireRole("admin");

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-10">
      <AdminNav current="security" />
      <p className="text-sm text-ink-muted">
        Логин и пароль администратора. И то и другое меняется с подтверждением текущего пароля, и
        каждая смена завершает все сессии — войти придётся заново. Обе записываются в журнал.
      </p>

      {/* the password first, because that is what somebody opening a screen called "Доступ"
        has come to change — and because a form asking for a password that quietly does
        something else is how it went wrong before */}
      <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
        <h2 className="font-medium">Пароль</h2>
        <PasswordChangeForm />
        <p className="text-sm text-ink-muted">
          Тот же экран доступен всем по адресу{" "}
          <Link href="/password" className="text-brand">
            /password
          </Link>
          . Если пароль потерян совсем, доступ восстанавливается только на сервере:{" "}
          <code className="px-1">bootstrap_admin --reset-password</code>.
        </p>
      </section>

      <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
        <h2 className="font-medium">Логин</h2>
        <p className="text-sm text-ink-muted">Сейчас: {user.email}</p>
        <EmailChangeForm />
      </section>
    </main>
  );
}
