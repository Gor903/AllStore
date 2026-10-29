"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * The token comes from the address bar, so it never goes through a field anybody can see or
 * a browser can remember. The page it sits on is served with `Referrer-Policy: no-referrer`
 * — without that, following any link from here would hand the token to whatever was linked.
 */
export function ResetPasswordForm({ token }: { token: string }) {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [mismatch, setMismatch] = useState(false);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const chosen = String(form.get("password"));
    // caught here rather than by the server: it is a typo, not a refusal
    if (chosen !== String(form.get("confirmation"))) {
      setMismatch(true);
      setError(null);
      return;
    }
    setMismatch(false);
    setPending(true);
    setError(null);
    const result = await apiPost("/auth/password-reset/confirm", { token, password: chosen });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    // the reset ended every session there was, so there is nowhere to go but in again
    router.push("/login");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <Field
        label="Новый пароль"
        name="password"
        type="password"
        autoComplete="new-password"
        error={error?.fieldErrors["password"]}
      />
      <Field
        label="Новый пароль ещё раз"
        name="confirmation"
        type="password"
        autoComplete="new-password"
        error={mismatch ? "Пароли не совпадают" : undefined}
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
        {pending ? "Меняем…" : "Задать пароль"}
      </button>
    </form>
  );
}
