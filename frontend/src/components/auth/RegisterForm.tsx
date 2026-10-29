"use client";

import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { GoogleButton } from "@/components/auth/GoogleButton";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

type Account = "buyer" | "seller";

/**
 * Answers the same way whether the address was free or taken, because the server does.
 *
 * It used to send people straight into the cabinet, which only worked because a free address
 * got a session and a taken one got a refusal — the difference anybody could read off the
 * form. Now registration promises a letter and nothing else, and signing in happens after
 * the address has answered.
 */
export function RegisterForm() {
  const [sent, setSent] = useState(false);
  const [account, setAccount] = useState<Account>("buyer");
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const phone = String(form.get("phone") ?? "").trim();
    const payload = {
      email: form.get("email"),
      password: form.get("password"),
      ...(phone ? { phone } : {}),
      ...(account === "seller"
        ? { legal_name: form.get("legal_name"), display_name: form.get("display_name") }
        : {}),
    };
    const result = await apiPost(`/auth/register/${account}`, payload);
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
        Если адрес свободен, мы отправили на него письмо со ссылкой для подтверждения. Откройте её,
        и можно будет войти.
      </p>
    );
  }

  return (
    <>
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <fieldset className="flex gap-2" aria-label="Тип аккаунта">
          {(["buyer", "seller"] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={account === value}
              onClick={() => {
                setAccount(value);
              }}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm ${
                account === value ? "border-brand text-brand" : "border-ink-muted/30"
              }`}
            >
              {value === "buyer" ? "Покупатель" : "Продавец"}
            </button>
          ))}
        </fieldset>

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
          autoComplete="new-password"
          error={error?.fieldErrors["password"]}
        />
        <Field
          label="Телефон (необязательно)"
          name="phone"
          type="tel"
          required={false}
          autoComplete="tel"
          error={error?.fieldErrors["phone"]}
        />

        {account === "seller" ? (
          <>
            <Field
              label="Юридическое название"
              name="legal_name"
              error={error?.fieldErrors["legal_name"]}
            />
            <Field
              label="Название магазина"
              name="display_name"
              error={error?.fieldErrors["display_name"]}
            />
          </>
        ) : null}

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
          {pending ? "Создаём аккаунт…" : "Зарегистрироваться"}
        </button>
      </form>

      <div className="flex items-center gap-3 text-xs text-ink-muted">
        <span className="h-px flex-1 bg-ink-muted/20" />
        или
        <span className="h-px flex-1 bg-ink-muted/20" />
      </div>
      {/* inside the form component because the role it carries is the tab above it */}
      <GoogleButton role={account} />
    </>
  );
}
