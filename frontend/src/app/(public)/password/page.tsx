import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PasswordChangeForm } from "@/components/auth/PasswordChangeForm";
import { getCurrentUser } from "@/lib/dal";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Пароль",
  robots: { index: false, follow: false },
};

/**
 * Outside the guarded groups on purpose: this is the one screen an account owing a password
 * change may reach, and `requireUser` sends it here. Reading the user through `getCurrentUser`
 * instead would make that redirect a loop.
 */
export default async function PasswordPage() {
  const user = await getCurrentUser();
  if (user === null) {
    redirect("/login");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="text-2xl font-semibold">
        {user.must_change_password ? "Задайте свой пароль" : "Смена пароля"}
      </h1>
      <p className="text-sm text-ink-muted">
        {user.must_change_password
          ? "Текущий пароль выдан вместе с доступом и известен тем, кто его выдавал. Пока он не заменён, остальная площадка закрыта."
          : "После смены все сессии завершатся, включая эту, и войти нужно будет заново."}
      </p>
      <PasswordChangeForm />
    </main>
  );
}
