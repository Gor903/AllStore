"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import type { User } from "@/lib/api";
import { SECOND_FACTOR_REQUIRED_CODE } from "@/lib/api-codes";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";
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

/**
 * Two steps when the account has an authenticator, one when it does not.
 *
 * The server decides which: a correct password for an account with a second factor opens no
 * session and answers `totp_required`, leaving a short-lived note in a cookie. The code goes
 * to a different route, which is what finally opens the session.
 *
 * `paused` also arrives set from the server, through `?totp=1` — that is how the Google
 * callback hands over, having nowhere to put a JSON refusal a browser can read.
 */
export function LoginForm({ next, paused = false }: { next: string | null; paused?: boolean }) {
  const router = useRouter();
  const [awaitingCode, setAwaitingCode] = useState(paused);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  function land(user: User) {
    // where they were going wins over where their role lives: being bounced to the login
    // screen and then somewhere else entirely is the thing `next` exists to prevent
    router.push(destinationFor(user, next));
    // the session lives in httpOnly cookies, so server components must re-read it
    router.refresh();
  }

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
      if (result.error.code === SECOND_FACTOR_REQUIRED_CODE) {
        setAwaitingCode(true);
        return;
      }
      setError(result.error);
      return;
    }
    land(result.data);
  }

  async function onCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost<User>("/auth/login/totp", { code: form.get("code") });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    land(result.data);
  }

  // The two forms are keyed apart so React builds a new input rather than reusing the
  // password's. Both branches return a `<form>`, and without distinct keys the reconciler
  // keeps the same DOM node — an uncontrolled field holds whatever was typed into it, so the
  // password would have appeared, in clear text, in the box asking for a code.
  if (awaitingCode) {
    return (
      <form key="code" onSubmit={onCode} className="flex flex-col gap-4" noValidate>
        <p className="text-sm text-ink-muted">
          Откройте приложение-аутентификатор и введите код. Если телефона нет под рукой — подойдёт
          один из резервных кодов.
        </p>
        <Field
          label="Код"
          name="code"
          // the browser offers the code it read from an SMS or an authenticator
          autoComplete="one-time-code"
          error={error?.fieldErrors["code"]}
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
          {pending ? "Проверяем…" : "Подтвердить"}
        </button>
      </form>
    );
  }

  return (
    <form key="credentials" onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
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
