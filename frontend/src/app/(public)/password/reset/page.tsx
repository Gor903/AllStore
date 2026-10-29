import type { Metadata } from "next";
import Link from "next/link";

import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Новый пароль",
  robots: { index: false, follow: false },
};

/**
 * Where the link in the letter lands.
 *
 * Whether the token is any good is the server's question, asked when the form is submitted —
 * checking it on arrival would turn this page into a way of finding out which tokens are
 * live, and would spend a one-time token on somebody merely opening the page.
 */
export default async function ResetPasswordPage({ searchParams }: PageProps<"/password/reset">) {
  const { token } = await searchParams;
  const given = typeof token === "string" ? token : "";

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="text-2xl font-semibold">Новый пароль</h1>
      {given === "" ? (
        <p className="text-sm text-ink-muted">
          В ссылке нет токена. Откройте письмо ещё раз или{" "}
          <Link href="/password/forgot" className="text-brand">
            запросите новую ссылку
          </Link>
          .
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-muted">
            После смены все сессии завершатся — войти нужно будет заново.
          </p>
          <ResetPasswordForm token={given} />
          <p className="text-sm text-ink-muted">
            Ссылка устарела?{" "}
            <Link href="/password/forgot" className="text-brand">
              Запросить новую
            </Link>
          </p>
        </>
      )}
    </main>
  );
}
