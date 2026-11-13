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

/**
 * A path on this host, and nothing that leaves it.
 *
 * One leading slash is a path; two is a host. `//evil.example` passed a `startsWith("/")`
 * check and arrived at `router.push` as an absolute address, which made the sign-in screen a
 * redirector anybody could aim anywhere — somebody signs in on the real domain and lands on a
 * look-alike asking them to sign in again. A backslash is here because browsers normalise it.
 */
function onThisHost(next: string): boolean {
  return next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\");
}

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const signedIn = await getCurrentUser();
  if (signedIn !== null) {
    redirect(homeFor(signedIn.role));
  }
  const { next } = await searchParams;
  // null means "nowhere in particular": then the form lands them by role, which it can only
  // know once the answer comes back
  const target = typeof next === "string" && onThisHost(next) ? next : null;

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="text-2xl font-semibold">Вход</h1>
      <LoginForm next={target} />
      <p className="text-sm text-ink-muted">
        <Link href="/password/forgot" className="text-brand">
          Забыли пароль?
        </Link>
      </p>
      <p className="text-sm text-ink-muted">
        Нет аккаунта?{" "}
        <Link href="/register" className="text-brand">
          Зарегистрироваться
        </Link>
      </p>
    </main>
  );
}
