"use client";

import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * Asking to move, not moving. Nothing changes until somebody opens the letter at the new
 * address — so this screen stays where it is and the session is left alone. It used to send
 * people to the login page, which was right when the change took effect on submit and is a
 * lie now.
 */
export function EmailChangeForm() {
  const [asked, setAsked] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost("/auth/email", {
      email: form.get("email"),
      current_password: form.get("current_password"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setAsked(true);
  }

  if (asked) {
    return (
      <p className="text-sm text-ink-muted" role="status">
        Ссылка отправлена на новый адрес. Пока он не подтверждён, вход по старому продолжает
        работать. На старый адрес ушло уведомление — если смену запрашивали не вы, смените пароль.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      {/* deliberately empty: prefilled with the current address, this field invites a
        submission that changes nothing, ends every session and says it succeeded. The
        address as it stands is shown above the form instead. */}
      <Field
        label="Новый email"
        name="email"
        type="email"
        autoComplete="email"
        error={error?.fieldErrors["email"]}
      />
      <Field
        label="Текущий пароль"
        name="current_password"
        type="password"
        autoComplete="current-password"
        error={error?.fieldErrors["current_password"]}
      />
      {error && Object.keys(error.fieldErrors).length === 0 ? (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Меняем…" : "Сменить логин"}
      </button>
    </form>
  );
}
