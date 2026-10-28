"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";
import type { User } from "@/lib/api";

/**
 * Appoints a moderator: an address and a password the administrator hands over.
 *
 * The password is typed here rather than generated, because it has to be passed on by hand
 * anyway — and a value the administrator chose is one they can read back off their own notes
 * if the message never arrived. It is temporary either way: the moderator cannot use the
 * platform until they replace it, which is what makes it safe to send in a chat message.
 */
export function AppointModerator() {
  const router = useRouter();
  const [appointed, setAppointed] = useState<string | null>(null);
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setAppointed(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const result = await apiPost<User>("/admin/moderators", {
      email: data.get("email"),
      password: data.get("password"),
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setAppointed(result.data.email);
    form.reset();
    router.refresh();
  }

  return (
    <section className="flex flex-col gap-3 rounded-card border border-ink-muted/20 p-4">
      <h2 className="font-medium">Завести модератора</h2>
      <p className="text-sm text-ink-muted">
        Передайте ему адрес и этот пароль. Пароль временный: войти по нему можно один раз, и до тех
        пор, пока модератор не задаст свой, площадка для него закрыта.
      </p>
      <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <Field
              label="Email"
              name="email"
              type="email"
              autoComplete="off"
              error={error?.fieldErrors["email"]}
            />
          </div>
          <div className="min-w-64 flex-1">
            <Field
              label="Временный пароль"
              name="password"
              type="text"
              autoComplete="off"
              error={error?.fieldErrors["password"]}
            />
          </div>
          <button
            type="submit"
            disabled={pending}
            className="rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
          >
            {pending ? "Заводим…" : "Завести"}
          </button>
        </div>
        {error && Object.keys(error.fieldErrors).length === 0 ? (
          <p role="alert" className="text-sm text-danger">
            {error.message}
          </p>
        ) : null}
      </form>

      {appointed === null ? null : (
        <p role="status" className="rounded-lg border border-brand/40 bg-brand/5 p-3 text-sm">
          Модератор <span className="font-medium">{appointed}</span> заведён. Передайте ему адрес и
          пароль, который вы только что задали.
        </p>
      )}
    </section>
  );
}
