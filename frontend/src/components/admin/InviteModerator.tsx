"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { InvitationCreated } from "@/lib/api";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * Issues an invitation and shows its link once.
 *
 * Once, because the backend keeps only a hash of the secret: there is nothing to look up
 * later. Mail delivery is not wired up yet (ADR 5), so until it is, the link is copied from
 * here by hand — and the screen says so rather than letting an administrator assume a letter
 * went out.
 */
export function InviteModerator() {
  const router = useRouter();
  const [issued, setIssued] = useState<{ email: string; link: string } | null>(null);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setIssued(null);
    const form = event.currentTarget;
    const email = String(new FormData(form).get("email") ?? "").trim();
    const result = await apiPost<InvitationCreated>("/admin/moderator-invitations", { email });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    const link = `${window.location.origin}/register/moderator?token=${encodeURIComponent(
      result.data.token,
    )}&email=${encodeURIComponent(result.data.invitation.email)}`;
    setIssued({ email: result.data.invitation.email, link });
    setCopied(false);
    form.reset();
    router.refresh();
  }

  async function onCopy() {
    if (issued === null) {
      return;
    }
    await navigator.clipboard.writeText(issued.link);
    setCopied(true);
  }

  return (
    <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
      <h2 className="font-medium">Пригласить модератора</h2>
      <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2" noValidate>
        <label className="flex min-w-64 flex-1 flex-col gap-1 text-sm">
          <span className="font-medium">Email</span>
          <input
            name="email"
            type="email"
            required
            autoComplete="off"
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none focus:border-brand"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {pending ? "Создаём…" : "Создать приглашение"}
        </button>
      </form>

      {error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      )}

      {issued === null ? null : (
        <div className="flex flex-col gap-2 rounded-lg border border-brand/40 bg-brand/5 p-3 text-sm">
          <p className="font-medium">Ссылка для {issued.email}</p>
          <p className="text-ink-muted">
            Показывается один раз: в базе хранится только отпечаток. Отправка писем ещё не настроена
            — передайте ссылку сами. Если потеряли, отзовите приглашение и создайте новое.
          </p>
          <code className="overflow-x-auto rounded-lg bg-surface px-3 py-2 text-xs">
            {issued.link}
          </code>
          <button
            type="button"
            onClick={() => void onCopy()}
            className="self-start rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium"
          >
            {copied ? "Скопировано" : "Скопировать ссылку"}
          </button>
        </div>
      )}
    </section>
  );
}
