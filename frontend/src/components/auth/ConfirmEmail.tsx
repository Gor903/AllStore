"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { apiPost } from "@/lib/browser-api";

type Outcome = { done: true; message: string } | { done: false; message: string } | null;

/**
 * Spends the link the moment the page opens.
 *
 * A button would be safer against a mail client that follows links to preview them — and
 * worse for everybody else, who would arrive at a page whose only content is a second thing
 * to click. The link is single-use either way; a preview that spends it costs one resend.
 */
export function ConfirmEmail({ token }: { token: string }) {
  const [outcome, setOutcome] = useState<Outcome>(null);
  // React mounts twice in development, and the second attempt would meet a spent link
  const started = useRef(false);

  useEffect(() => {
    if (started.current) {
      return;
    }
    started.current = true;
    void (async () => {
      const result = await apiPost<{ message: string }>("/auth/email/confirm", { token });
      setOutcome(
        result.ok
          ? { done: true, message: result.data.message }
          : { done: false, message: result.error.message },
      );
    })();
  }, [token]);

  if (outcome === null) {
    return <p className="text-sm text-ink-muted">Подтверждаем…</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <p role={outcome.done ? "status" : "alert"} className={outcome.done ? "" : "text-danger"}>
        {outcome.message}
      </p>
      <Link href={outcome.done ? "/dashboard" : "/login"} className="text-sm text-brand">
        {outcome.done ? "В кабинет" : "Ко входу"}
      </Link>
    </div>
  );
}
