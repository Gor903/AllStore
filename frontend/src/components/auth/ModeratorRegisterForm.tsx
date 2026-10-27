"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * Accepting an invitation. The address is read from the link and shown rather than typed:
 * it is what the invitation is bound to, and a stranger retyping it is exactly the case the
 * binding exists to refuse.
 */
export function ModeratorRegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const email = params.get("email") ?? "";
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost("/auth/register/moderator", {
      token,
      email,
      password: form.get("password"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    router.push("/moderation");
    router.refresh();
  }

  if (token === "" || email === "") {
    return (
      <p role="alert" className="text-sm text-danger">
        Ссылка неполная. Попросите администратора выдать приглашение заново.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <p className="text-sm">
        Приглашение для <span className="font-medium">{email}</span>
      </p>
      <Field
        label="Пароль"
        name="password"
        type="password"
        autoComplete="new-password"
        error={error?.fieldErrors["password"]}
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
        {pending ? "Принимаем приглашение…" : "Стать модератором"}
      </button>
    </form>
  );
}
