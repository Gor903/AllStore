import type { Metadata } from "next";
import Link from "next/link";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Забыли пароль",
  robots: { index: false, follow: false },
};

export default function ForgotPasswordPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="text-2xl font-semibold">Забыли пароль</h1>
      <p className="text-sm text-ink-muted">
        Укажите адрес, на который зарегистрирован аккаунт. Мы пришлём ссылку, по которой можно
        задать новый пароль.
      </p>
      <ForgotPasswordForm />
      <p className="text-sm text-ink-muted">
        Вспомнили?{" "}
        <Link href="/login" className="text-brand">
          Войти
        </Link>
      </p>
    </main>
  );
}
