"use client";

import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * The answer is the same whether the address is known or not, and this screen has to be too.
 *
 * It would be friendlier to say "no such account" and save somebody the wait for a letter
 * that is not coming. It would also turn this form into a way of asking whether a particular
 * person has an account here, which is not ours to answer.
 */
export function ForgotPasswordForm() {
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost("/auth/password-reset/request", { email: form.get("email") });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <p className="text-sm text-ink-muted" role="status">
        Если аккаунт с таким адресом есть, мы отправили на него письмо со ссылкой. Ссылка действует
        два часа и срабатывает один раз.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <Field
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        error={error?.fieldErrors["email"]}
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
        {pending ? "Отправляем…" : "Прислать ссылку"}
      </button>
    </form>
  );
}
