import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { RegisterForm } from "@/components/auth/RegisterForm";
import { getCurrentUser } from "@/lib/dal";

export const metadata: Metadata = {
  title: "Регистрация",
  robots: { index: false, follow: false },
};

export default async function RegisterPage() {
  if ((await getCurrentUser()) !== null) {
    redirect("/dashboard");
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6 py-12">
      <h1 className="text-2xl font-semibold">Регистрация</h1>
      <p className="text-sm text-ink-muted">
        Магазин продавца проходит проверку модератором до публикации.
      </p>
      <RegisterForm />
      <p className="text-sm text-ink-muted">
        Уже есть аккаунт?{" "}
        <Link href="/login" className="text-brand">
          Войти
        </Link>
      </p>
    </main>
  );
}
