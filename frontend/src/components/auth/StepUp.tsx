"use client";

import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * Asking for the password again, for the actions an unattended screen must not be enough for.
 *
 * The server has demanded this since stage 4 — appointing a moderator, handing over the
 * administrator role, attaching another way in — and until now there was no screen that could
 * answer it. Signing in grants the claim for ten minutes, so the actions worked if you were
 * quick and refused with no way forward if you were not. The refusal even said what to do;
 * there was simply nowhere to do it.
 */
export function StepUp({
  reason,
  onDone,
  onCancel,
}: {
  reason: string;
  onDone: () => void;
  onCancel?: () => void;
}) {
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost("/auth/verify", { password: form.get("password") });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    onDone();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
      <p className="text-sm text-ink-muted">{reason}</p>
      <Field
        label="Пароль"
        name="password"
        type="password"
        autoComplete="current-password"
        error={error?.fieldErrors["password"]}
      />
      {error && Object.keys(error.fieldErrors).length === 0 ? (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={pending}
          className="rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {pending ? "Проверяем…" : "Подтвердить"}
        </button>
        {onCancel === undefined ? null : (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-ink-muted/30 px-4 py-2 text-sm"
          >
            Отмена
          </button>
        )}
      </div>
    </form>
  );
}
