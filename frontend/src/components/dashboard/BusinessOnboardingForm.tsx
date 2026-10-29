"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/auth/Field";
import { apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

/**
 * The questions a shop cannot exist without, asked of a seller who was never asked them.
 *
 * Registering with a password asks for all of this on the way in. Google asks for none of it
 * and cannot — it knows an address, and a shop needs a legal name and a name to trade under.
 * Without this screen such an account is a seller with nothing to sell from and no way to fix
 * that.
 */
export function BusinessOnboardingForm() {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const phone = String(form.get("phone") ?? "").trim();
    const result = await apiPost("/users/me/business", {
      legal_name: form.get("legal_name"),
      display_name: form.get("display_name"),
      ...(phone ? { phone } : {}),
    });
    if (!result.ok) {
      setPending(false);
      setError(result.error);
      return;
    }
    // the cabinet reads the business on the server, so a refresh is what makes it appear
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
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
      <Field
        label="Телефон (необязательно)"
        name="phone"
        type="tel"
        required={false}
        autoComplete="tel"
        error={error?.fieldErrors["phone"]}
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
        {pending ? "Отправляем…" : "Отправить на проверку"}
      </button>
    </form>
  );
}
