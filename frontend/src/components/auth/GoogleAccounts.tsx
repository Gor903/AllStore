"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StepUp } from "@/components/auth/StepUp";
import { apiDelete } from "@/lib/browser-api";
import { API_PREFIX, env } from "@/lib/env";
import type { FormError } from "@/lib/errors";

export type GoogleIdentity = { id: string; provider: string; email_at_link: string };

/**
 * Attaching and detaching Google, from inside an account that already exists.
 *
 * The journey leaves the site, so this is a link rather than a request: the browser goes to
 * Google and comes back to the callback, which lands it here again. Nothing to await, and
 * nothing useful to do with a failure except read the page it returns to.
 *
 * Behind a step-up, because adding a way into an account is as grave as changing the
 * password — an unattended screen must not be enough. Staff may attach only a Google account
 * on the account's own address; the server says so and the message explains why.
 */
export function GoogleAccounts({
  identities,
  configured,
  staff,
  email,
}: {
  identities: GoogleIdentity[];
  configured: boolean;
  staff: boolean;
  email: string;
}) {
  const router = useRouter();
  // "none" → the button; "proving" → the password; "ready" → the link out to Google
  const [stage, setStage] = useState<"none" | "proving" | "ready">("none");
  const [error, setError] = useState<FormError | null>(null);

  async function detach(id: string) {
    setError(null);
    const result = await apiDelete(`/auth/google/identities/${id}`);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    router.refresh();
  }

  if (!configured) {
    return null;
  }

  return (
    <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
      <h2 className="font-medium">Вход через Google</h2>

      {identities.length === 0 ? (
        <p className="text-sm text-ink-muted">
          Пока не привязан. Привязка добавляет второй способ войти — пароль продолжает работать.
          {staff ? ` Для вашей роли подойдёт только аккаунт Google на адресе ${email}.` : ""}
        </p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {identities.map((identity) => (
            <li key={identity.id} className="flex items-center justify-between gap-3">
              <span>{identity.email_at_link}</span>
              <button
                type="button"
                onClick={() => {
                  void detach(identity.id);
                }}
                className="rounded-lg border border-ink-muted/30 px-3 py-1 text-sm"
              >
                Отвязать
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && Object.keys(error.fieldErrors).length === 0 ? (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      ) : null}

      {identities.length > 0 ? null : stage === "proving" ? (
        <StepUp
          reason="Подтвердите пароль — вы добавляете способ войти в аккаунт."
          onDone={() => {
            setStage("ready");
          }}
          onCancel={() => {
            setStage("none");
          }}
        />
      ) : stage === "ready" ? (
        // A link rather than a redirect in code: the next stop is Google's own page at
        // Google's own address, which is a top-level navigation by nature — the same reason
        // the sign-in button is a link. The step-up above is what it waited for.
        <Link
          href={`${env.apiUrl}${API_PREFIX}/auth/google/link`}
          prefetch={false}
          className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white"
        >
          Продолжить с Google
        </Link>
      ) : (
        <button
          type="button"
          onClick={() => {
            setStage("proving");
          }}
          className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white"
        >
          Привязать Google
        </button>
      )}
    </section>
  );
}
