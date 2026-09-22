"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import type { Store } from "@/lib/api";
import { apiPatch } from "@/lib/browser-api";
import type { FormError } from "@/lib/errors";
import { PALETTE, swatchOf } from "@/lib/palette";

type StoreSettingsFormProps = {
  store: Store;
};

/** An empty textarea means "no description", which the backend spells as null. */
function described(value: FormDataEntryValue | null): string | null {
  const text = String(value ?? "").trim();
  return text === "" ? null : text;
}

export function StoreSettingsForm({ store }: StoreSettingsFormProps) {
  const router = useRouter();
  const [chosen, setChosen] = useState(() => swatchOf(store.primary_color, store.secondary_color));
  const [error, setError] = useState<FormError | null>(null);
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);

  // A colour set before this screen existed joins the palette rather than leaving every
  // swatch unselected: the seller has to see what their shop wears now. Computed once, so
  // moving to a palette colour does not make the old one vanish beyond recall.
  const [offered] = useState(() => {
    const worn = swatchOf(store.primary_color, store.secondary_color);
    return PALETTE.includes(worn) ? PALETTE : [...PALETTE, worn];
  });

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setSaved(false);
    const form = new FormData(event.currentTarget);
    const result = await apiPatch<Store>("/stores/me", {
      description: described(form.get("description")),
      primary_color: chosen.primary,
      secondary_color: chosen.secondary,
    });
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
      {/* the hint sits outside the label, so it is described rather than read as the name */}
      <div className="flex flex-col gap-1 text-sm">
        <label htmlFor="store-description" className="font-medium">
          Описание магазина
        </label>
        <textarea
          id="store-description"
          name="description"
          rows={4}
          maxLength={2000}
          aria-describedby="store-description-hint"
          defaultValue={store.description ?? ""}
          className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2"
        />
        <p id="store-description-hint" className="text-ink-muted">
          Покупатель читает его на витрине и в списке магазинов. Чем занимаетесь, откуда
          доставляете, что важно знать до заказа.
        </p>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Цвета магазина</legend>
        <div className="flex flex-wrap gap-2">
          {offered.map((swatch) => {
            const picked = swatch.name === chosen.name;
            return (
              <button
                key={swatch.name}
                type="button"
                onClick={() => setChosen(swatch)}
                aria-pressed={picked}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                  picked ? "border-brand font-medium" : "border-ink-muted/30"
                }`}
              >
                <span
                  aria-hidden
                  className="h-4 w-4 rounded-full border border-ink-muted/20"
                  style={{ background: swatch.primary ?? "transparent" }}
                />
                {swatch.name}
              </button>
            );
          })}
        </div>
        <p className="text-sm text-ink-muted">
          Готовые пары, а не свободный выбор: на каждой из них белый текст кнопок остаётся читаемым.
        </p>
      </fieldset>

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
        {pending ? "Сохраняем…" : "Сохранить"}
      </button>
    </form>
  );
}
