import type { Metadata } from "next";
import Link from "next/link";

import { ConfirmEmail } from "@/components/auth/ConfirmEmail";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Подтверждение адреса",
  robots: { index: false, follow: false },
};

/**
 * Where the link in the letter lands. Needs no session of its own: the token is the proof,
 * and whoever opens it may well be on a device that was never signed in.
 */
export default async function ConfirmEmailPage({ searchParams }: PageProps<"/email/confirm">) {
  const { token } = await searchParams;
  const given = typeof token === "string" ? token : "";

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6">
      <h1 className="text-2xl font-semibold">Подтверждение адреса</h1>
      {given === "" ? (
        <p className="text-sm text-ink-muted">
          В ссылке нет токена. Откройте письмо ещё раз или запросите новое в{" "}
          <Link href="/dashboard" className="text-brand">
            кабинете
          </Link>
          .
        </p>
      ) : (
        <ConfirmEmail token={given} />
      )}
    </main>
  );
}
