"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent } from "react";

import type { Store } from "@/lib/api";
import { apiDelete, apiUploadPut } from "@/lib/browser-api";

type StoreImageFieldProps = {
  kind: "logo" | "banner";
  label: string;
  hint: string;
  currentUrl: string | null;
};

const PREVIEW = {
  logo: { width: 96, height: 96, className: "h-24 w-24 rounded-full object-cover" },
  banner: { width: 480, height: 120, className: "h-24 w-full rounded-card object-cover" },
} as const;

/** One picture per slot: uploading a second replaces the first, so there is no gallery here. */
export function StoreImageField({ kind, label, hint, currentUrl }: StoreImageFieldProps) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const preview = PREVIEW[kind];

  async function onPick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file === undefined) {
      return;
    }
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.set("file", file);
    const result = await apiUploadPut<Store>(`/stores/me/images/${kind}`, form);
    setBusy(false);
    // the same file picked twice in a row has to fire the change event again
    if (input.current !== null) {
      input.current.value = "";
    }
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  async function onRemove() {
    setBusy(true);
    setMessage(null);
    const result = await apiDelete<Store>(`/stores/me/images/${kind}`);
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">{label}</h3>
      {currentUrl === null ? (
        <p className="text-sm text-ink-muted">{hint}</p>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Image
            src={currentUrl}
            alt=""
            width={preview.width}
            height={preview.height}
            unoptimized
            className={preview.className}
          />
          <button
            type="button"
            onClick={() => void onRemove()}
            disabled={busy}
            className="text-xs text-danger disabled:opacity-60"
          >
            Удалить
          </button>
        </div>
      )}

      <label className="flex flex-col gap-1 text-sm">
        <span className="sr-only">{currentUrl === null ? label : `Заменить: ${label}`}</span>
        <input
          ref={input}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          onChange={(event) => void onPick(event)}
          disabled={busy}
          className="text-sm"
        />
        <span className="text-ink-muted">JPEG, PNG, GIF или WEBP, до 5 МБ.</span>
      </label>

      {message === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {message}
        </p>
      )}
    </section>
  );
}
