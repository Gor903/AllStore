"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Product } from "@/lib/api";
import { apiDelete, apiPost } from "@/lib/browser-api";

export function ProductActions({ product }: { product: Product }) {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const waiting = product.moderation_status === "pending";

  async function onSubmitForReview() {
    setBusy(true);
    setMessage(null);
    const result = await apiPost(`/products/${product.id}/submit`, {});
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  async function onArchive() {
    // archiving takes the product off the shelf for good as far as the seller is concerned
    if (!window.confirm(`Убрать «${product.name}» из магазина?`)) {
      return;
    }
    setBusy(true);
    setMessage(null);
    const result = await apiDelete(`/products/${product.id}`);
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.push("/dashboard");
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void onSubmitForReview()}
          disabled={busy || waiting}
          className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          {waiting ? "Уже на проверке" : "Отправить на проверку"}
        </button>
        <button
          type="button"
          onClick={() => void onArchive()}
          disabled={busy}
          className="rounded-lg border border-danger/40 px-4 py-2 text-sm font-medium text-danger disabled:opacity-60"
        >
          Убрать из магазина
        </button>
      </div>
      {message === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
