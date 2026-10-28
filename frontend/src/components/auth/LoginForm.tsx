"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";
import type { User } from "@/lib/api";
import { homeFor } from "@/lib/home";

/**
 * An account owing a password change goes to that screen and nowhere else: every other
 * route would bounce it here anyway, and the bounce reads as a page that failed to load.
 */
function destinationFor(user: User, next: string | null): string {
  if (user.must_change_password) {
    return "/password";
  }
  return next ?? homeFor(user.role);
}

export function LoginForm({ next }: { next: string | null }) {
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
    // where they were going wins over where their role lives: being bounced to the login
    // screen and then somewhere else entirely is the thing `next` exists to prevent
    router.push(destinationFor(result.data, next));
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
