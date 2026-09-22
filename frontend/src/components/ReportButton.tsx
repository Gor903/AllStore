"use client";

import { useState, type FormEvent } from "react";

import { apiPost } from "@/lib/browser-api";

type ReportButtonProps = {
  /** Exactly one of the two: a product by id, a shop by the address a visitor sees. */
  productId?: string;
  subdomain?: string;
  label: string;
};

const REASON_MAX_LENGTH = 1000;

/**
 * Works without an account: whoever has just been cheated is not going to register first.
 * The browser client sends the CSRF header only when the cookie exists, and a guest has
 * none — which is why this endpoint does not ask for one (see app/api/reports.py).
 */
export function ReportButton({ productId, subdomain, label }: ReportButtonProps) {
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = String(new FormData(event.currentTarget).get("reason") ?? "").trim();
    if (reason === "") {
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await apiPost("/reports", {
      ...(productId === undefined ? { subdomain } : { product_id: productId }),
      reason,
    });
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    setOpen(false);
    setSent(true);
  }

  if (sent) {
    // nothing about what happens next: what a moderator decides is not the reporter's business
    return <p className="text-sm text-ink-muted">Жалоба отправлена, модератор её посмотрит.</p>;
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="self-start text-sm text-ink-muted underline hover:text-danger"
      >
        {label}
      </button>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-2 rounded-card border border-ink-muted/25 p-3"
    >
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Что не так?</span>
        <textarea
          name="reason"
          rows={3}
          required
          maxLength={REASON_MAX_LENGTH}
          className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
        />
      </label>
      <p className="text-xs text-ink-muted">
        Жалобу читает модератор площадки. Продавец не увидит, кто пожаловался.
      </p>
      {message === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {message}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger disabled:opacity-60"
        >
          {busy ? "Отправляем…" : "Отправить"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          disabled={busy}
          className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm"
        >
          Отмена
        </button>
      </div>
    </form>
  );
}
