"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost } from "@/lib/browser-api";

/**
 * Answering a refusal.
 *
 * The button exists at all because `rejected` is deliberately not `blocked`: a refusal says
 * what is wrong and expects an answer, so the seller needs a way to give one without writing
 * to support.
 */
export function ResubmitBusiness() {
  const router = useRouter();
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    setBusy(true);
    setMessage(null);
    const result = await apiPost("/users/me/business/resubmit", {});
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => void onSubmit()}
        disabled={busy}
        className="self-start rounded-lg bg-brand px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {busy ? "Отправляем…" : "Отправить заявку снова"}
      </button>
      {message === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
