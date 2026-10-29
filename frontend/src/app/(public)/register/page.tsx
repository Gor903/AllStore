import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { GoogleButton } from "@/components/auth/GoogleButton";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { getCurrentUser } from "@/lib/dal";
import { homeFor } from "@/lib/home";

export const metadata: Metadata = {
  title: "Регистрация",
  robots: { index: false, follow: false },
};

export default async function RegisterPage() {
  const signedIn = await getCurrentUser();
  if (signedIn !== null) {
    redirect(homeFor(signedIn.role));
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6 py-12">
      <h1 className="text-2xl font-semibold">Регистрация</h1>
      <p className="text-sm text-ink-muted">
        Магазин продавца проходит проверку модератором до публикации.
      </p>
      <RegisterForm />
      <div className="flex items-center gap-3 text-xs text-ink-muted">
        <span className="h-px flex-1 bg-ink-muted/20" />
        или
        <span className="h-px flex-1 bg-ink-muted/20" />
      </div>
      <GoogleButton role="buyer" />
      <p className="text-sm text-ink-muted">
        Уже есть аккаунт?{" "}
        <Link href="/login" className="text-brand">
          Войти
        </Link>
      </p>
    </main>
  );
}
