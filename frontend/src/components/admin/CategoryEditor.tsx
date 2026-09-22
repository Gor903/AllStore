"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { AdminCategory } from "@/lib/api";
import { apiPatch, apiPost } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";

type CategoryRowProps = {
  category: AdminCategory;
  nested?: boolean;
};

/** Renaming and hiding in place. Nothing here deletes: a deleted category would take the
 * products filed under it with it, which is why hiding exists. */
export function CategoryRow({ category, nested = false }: CategoryRowProps) {
  const router = useRouter();
  const [name, setName] = useState(category.name);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const hidden = category.status === "hidden";

  async function save(body: Record<string, string>) {
    setBusy(true);
    setMessage(null);
    const result = await apiPatch<AdminCategory>(`/admin/categories/${category.id}`, body);
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <li className={`flex flex-col gap-1 p-3 ${nested ? "pl-8" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label={`Название категории ${category.slug}`}
          className="min-w-48 flex-1 rounded-lg border border-ink-muted/30 bg-surface px-2 py-1 text-sm"
        />
        <code className="text-xs text-ink-muted">{category.slug}</code>
        <button
          type="button"
          onClick={() => void save({ name })}
          disabled={busy || name.trim() === "" || name === category.name}
          className="rounded-lg border border-ink-muted/30 px-3 py-1 text-sm disabled:opacity-60"
        >
          Переименовать
        </button>
        <button
          type="button"
          onClick={() => void save({ status: hidden ? "active" : "hidden" })}
          disabled={busy}
          className={
            hidden
              ? "rounded-lg bg-brand px-3 py-1 text-sm font-medium text-white disabled:opacity-60"
              : "rounded-lg border border-danger/40 px-3 py-1 text-sm text-danger disabled:opacity-60"
          }
        >
          {hidden ? "Вернуть в каталог" : "Скрыть"}
        </button>
        {hidden ? <span className="text-xs text-ink-muted">скрыта от покупателя</span> : null}
      </div>
      {message === null ? null : (
        <p role="alert" className="text-xs text-danger">
          {message}
        </p>
      )}
    </li>
  );
}

type CategoryCreateFormProps = {
  parents: AdminCategory[];
};

export function CategoryCreateForm({ parents }: CategoryCreateFormProps) {
  const router = useRouter();
  const [error, setError] = useState<FormError | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const parent = String(form.get("parent_id") ?? "");
    const result = await apiPost<AdminCategory>("/admin/categories", {
      name: form.get("name"),
      slug: form.get("slug"),
      // an empty choice means a top-level category, which the backend spells as null
      parent_id: parent === "" ? null : parent,
    });
    setPending(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    event.currentTarget.reset();
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3" noValidate>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Название</span>
          <input
            name="name"
            required
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Адрес</span>
          <input
            name="slug"
            required
            placeholder="pet-food"
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Раздел</span>
          <select
            name="parent_id"
            defaultValue=""
            className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
          >
            <option value="">— верхний уровень —</option>
            {parents.map((parent) => (
              <option key={parent.id} value={parent.id}>
                {parent.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-sm text-ink-muted">
        Адрес — то, что покупатель увидит в ссылке фильтра: латинские буквы, цифры и дефисы.
        Поменять его потом нельзя, ссылка может быть уже сохранена.
      </p>

      {error === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {error.message}
        </p>
      )}

      <button
        type="submit"
        disabled={pending}
        className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {pending ? "Добавляем…" : "Добавить категорию"}
      </button>
    </form>
  );
}
