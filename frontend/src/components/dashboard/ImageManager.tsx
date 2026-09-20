"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useRef, useState, type ChangeEvent } from "react";

import type { ProductImage } from "@/lib/api";
import { apiDelete, apiUpload } from "@/lib/browser-api";

type ImageManagerProps = {
  productId: string;
  images: ProductImage[];
  max: number;
};

export function ImageManager({ productId, images, max }: ImageManagerProps) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onPick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file === undefined) {
      return;
    }
    setBusy(true);
    setMessage(null);
    const form = new FormData();
    form.set("file", file);
    form.set("alt_text", file.name);
    const result = await apiUpload(`/products/${productId}/images`, form);
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

  async function onRemove(imageId: string) {
    setBusy(true);
    setMessage(null);
    const result = await apiDelete(`/products/${productId}/images/${imageId}`);
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <h2 className="font-medium">Фотографии</h2>
        <span className="text-sm text-ink-muted">
          {images.length} из {max}
        </span>
      </div>

      {images.length === 0 ? (
        <p className="text-sm text-ink-muted">
          Без фотографии товар выглядит пустым местом в каталоге.
        </p>
      ) : (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-5">
          {images.map((image) => (
            <li key={image.id} className="flex flex-col gap-1">
              <div className="relative aspect-square overflow-hidden rounded-lg bg-surface-muted">
                <Image
                  src={image.image_url}
                  alt={image.alt_text ?? ""}
                  fill
                  sizes="20vw"
                  className="object-cover"
                />
              </div>
              <button
                type="button"
                onClick={() => void onRemove(image.id)}
                disabled={busy}
                className="text-xs text-danger disabled:opacity-60"
              >
                Удалить
              </button>
            </li>
          ))}
        </ul>
      )}

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Добавить фото</span>
        <input
          ref={input}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          onChange={(event) => void onPick(event)}
          disabled={busy || images.length >= max}
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
