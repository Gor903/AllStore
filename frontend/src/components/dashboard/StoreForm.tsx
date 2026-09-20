"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import type { Store } from "@/lib/api";
import { apiPost } from "@/lib/browser-api";
import { env } from "@/lib/env";
import type { FormError } from "@/lib/errors";

export function StoreForm() {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const result = await apiPost<Store>("/stores", { subdomain: form.get("subdomain") });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
      <Field label="Адрес магазина" name="subdomain" error={error?.fieldErrors["subdomain"]} />
      <p className="text-sm text-ink-muted">
        Магазин откроется по адресу <code>имя.{env.baseDomain}</code>. Латинские буквы, цифры и
        дефис, от 3 до 63 символов. Изменить адрес потом нельзя.
      </p>
      {error && Object.keys(error.fieldErrors).length === 0 ? (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Создаём…" : "Создать магазин"}
      </button>
    </form>
  );
}
