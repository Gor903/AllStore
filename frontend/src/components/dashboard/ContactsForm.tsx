"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { Contact, ContactList } from "@/lib/api";
import { apiPut } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

type ContactsFormProps = {
  contacts: Contact[];
};

type Row = {
  platform: Contact["platform"];
  label: string;
  placeholder: string;
};

// phone-shaped platforms first: a buyer who wants to call should not hunt for the number
const ROWS: readonly Row[] = [
  { platform: "phone", label: "Телефон", placeholder: "+374 10 123456" },
  { platform: "whatsapp", label: "WhatsApp", placeholder: "+374 10 123456" },
  { platform: "viber", label: "Viber", placeholder: "+374 10 123456" },
  { platform: "telegram", label: "Telegram", placeholder: "@mystore или ссылка" },
  { platform: "instagram", label: "Instagram", placeholder: "@mystore или ссылка" },
  { platform: "facebook", label: "Facebook", placeholder: "mystore или ссылка" },
];

export function ContactsForm({ contacts }: ContactsFormProps) {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);

  const current = new Map(contacts.map((contact) => [contact.platform, contact.value]));

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setSaved(false);
    const form = new FormData(event.currentTarget);
    // the whole set goes at once, so a field the seller emptied is a contact they removed
    const items = ROWS.map((row) => ({
      platform: row.platform,
      value: String(form.get(row.platform) ?? "").trim(),
    })).filter((item) => item.value !== "");

    const result = await apiPut<ContactList>("/stores/me/contacts", { items });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSaved(true);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div className="grid gap-3 sm:grid-cols-2">
        {ROWS.map((row) => (
          <label key={row.platform} className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{row.label}</span>
            <input
              name={row.platform}
              defaultValue={current.get(row.platform) ?? ""}
              placeholder={row.placeholder}
              className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
            />
          </label>
        ))}
      </div>

      <p className="text-sm text-ink-muted">
        Хотя бы один способ связи обязателен: корзины и оплаты на площадке нет, покупатель пишет или
        звонит вам напрямую. Пока контактов нет, товар не уходит на проверку.
      </p>

      {error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      )}
      {saved ? <p className="text-sm text-success">Сохранено.</p> : null}

      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Сохраняем…" : "Сохранить контакты"}
      </button>
    </form>
  );
}
