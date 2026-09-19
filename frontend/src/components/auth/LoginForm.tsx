"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";
import type { User } from "@/lib/api";

export function LoginForm({ next }: { next: string }) {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost<User>("/auth/login", {
      email: form.get("email"),
      password: form.get("password"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    router.push(next);
    // the session lives in httpOnly cookies, so server components must re-read it
    router.refresh();
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
      <button
        type="submit"
        disabled={pending}
        className="rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Входим…" : "Войти"}
      </button>
    </form>
  );
}
