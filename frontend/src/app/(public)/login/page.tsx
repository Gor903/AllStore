import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/auth/LoginForm";
import { getCurrentUser } from "@/lib/dal";
import { homeFor } from "@/lib/home";

export const metadata: Metadata = {
  title: "Вход",
  robots: { index: false, follow: false },
};

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const signedIn = await getCurrentUser();
  if (signedIn !== null) {
    redirect(homeFor(signedIn.role));
  }
  const { next } = await searchParams;
  // null means "nowhere in particular": then the form lands them by role, which it can only
  // know once the answer comes back
  const target = typeof next === "string" && next.startsWith("/") ? next : null;

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="text-2xl font-semibold">Вход</h1>
      <LoginForm next={target} />
      <p className="text-sm text-ink-muted">
        Нет аккаунта?{" "}
        <Link href="/register" className="text-brand">
          Зарегистрироваться
        </Link>
      </p>
    </main>
  );
}
