"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * Hands a moderator a new temporary password.
 *
 * There is no recovery link to send and nothing to wait for: the administrator already
 * decides who moderates, so letting them restore access is no new authority. The replacement
 * expires on first use exactly like the first one did.
 */
export function ResetModeratorPassword({ userId, email }: { userId: string; email: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = event.currentTarget;
    const result = await apiPost(`/admin/moderators/${userId}/password`, {
      password: new FormData(form).get("password"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setDone(true);
    setOpen(false);
    form.reset();
    router.refresh();
  }

  if (!open) {
    return (
      <div className="flex flex-col gap-1">
        <button
          type="button"
          onClick={() => {
            setOpen(true);
            setDone(false);
          }}
          className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium"
        >
          Выдать новый пароль
        </button>
        {done ? (
          <span role="status" className="text-xs text-ink-muted">
            Передан. До замены площадка для него закрыта.
          </span>
        ) : null}
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2" noValidate>
      <label className="flex flex-col gap-1 text-sm">
        <span className="sr-only">Новый временный пароль для {email}</span>
        <input
          name="password"
          type="text"
          required
          autoComplete="off"
          placeholder="Новый временный пароль"
          className="min-w-56 rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
        />
      </label>
      <button
        type="submit"
        disabled={pending}
        className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
      >
        {pending ? "Выдаём…" : "Выдать"}
      </button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="px-2 py-1.5 text-sm text-ink-muted"
      >
        Отмена
      </button>
      {error === null ? null : (
        <p role="alert" className="w-full text-sm text-danger">
          {error.message}
        </p>
      )}
    </form>
  );
}
