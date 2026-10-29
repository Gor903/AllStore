"use client";

import { useState } from "react";

import { apiPost } from "@/lib/browser-api";

/**
 * Shown to an account whose address has not answered yet.
 *
 * Worded as a thing to finish rather than a thing being withheld. Only one door is actually
 * closed — opening a shop — and saying so plainly is better than a banner that implies the
 * whole site is hostage: the second kind gets dismissed, and then nobody confirms anything.
 */
export function VerifyEmailNotice({ email, seller }: { email: string; seller: boolean }) {
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resend() {
    setPending(true);
    setError(null);
    const result = await apiPost("/auth/email/verify", {});
    setPending(false);
    if (!result.ok) {
      setError(result.error.message);
      return;
    }
    setSent(true);
  }

  return (
    <aside className="flex flex-col gap-2 rounded-card border border-brand/30 bg-brand/5 p-4">
      <p className="text-sm">
        Адрес <strong>{email}</strong> ещё не подтверждён.{" "}
        {seller
          ? "Пока он не подтверждён, магазин открыть нельзя."
          : "Подтвердите его, чтобы мы могли с вами связаться."}
      </p>
      {sent ? (
        <p className="text-sm text-ink-muted" role="status">
          Письмо отправлено, проверьте почту.
        </p>
      ) : (
        <button
          type="button"
          onClick={() => void resend()}
          disabled={pending}
          className="self-start text-sm text-brand disabled:opacity-60"
        >
          {pending ? "Отправляем…" : "Прислать письмо ещё раз"}
        </button>
      )}
      {error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
    </aside>
  );
}
