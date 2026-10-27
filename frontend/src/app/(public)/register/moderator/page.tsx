import type { Metadata } from "next";
import { Suspense } from "react";

import { ModeratorRegisterForm } from "@/components/auth/ModeratorRegisterForm";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Приглашение модератора",
  robots: { index: false, follow: false },
};

export default function ModeratorRegisterPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-6 px-6 py-12">
      <h1 className="text-2xl font-semibold">Приглашение модератора</h1>
      <p className="text-sm text-ink-muted">
        Ссылка работает один раз и только для адреса, на который выписана.
      </p>
      {/* the form reads the link's query, and that is a client-side read */}
      <Suspense fallback={<p className="text-sm text-ink-muted">Открываем приглашение…</p>}>
        <ModeratorRegisterForm />
      </Suspense>
    </main>
  );
}
