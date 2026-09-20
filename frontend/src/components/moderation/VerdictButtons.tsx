"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost } from "@/lib/browser-api";

export type Verdict = {
  label: string;
  /** Appended to the base path, e.g. "approve". */
  action: string;
  /** A verdict that takes something away has to say why. */
  reasonPrompt?: string;
  danger?: boolean;
};

type VerdictButtonsProps = {
  /** Where the decisions are posted, without the trailing action. */
  basePath: string;
  verdicts: Verdict[];
};

/**
 * The decisions of one row. A verdict that needs a reason opens a box for it instead of
 * firing at once — a refusal the seller cannot act on is not a refusal.
 */
export function VerdictButtons({ basePath, verdicts }: VerdictButtonsProps) {
  const router = useRouter();
  const [asking, setAsking] = useState<Verdict | null>(null);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function send(verdict: Verdict, withReason: string | null): Promise<void> {
    setBusy(true);
    setMessage(null);
    const result = await apiPost(
      `${basePath}/${verdict.action}`,
      withReason === null ? {} : { reason: withReason },
    );
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    setAsking(null);
    setReason("");
    router.refresh();
  }

  function onPick(verdict: Verdict): void {
    if (verdict.reasonPrompt === undefined) {
      void send(verdict, null);
      return;
    }
    setAsking(verdict);
    setMessage(null);
  }

  const style = (danger: boolean): string =>
    danger
      ? "rounded-lg border border-danger/40 px-3 py-1.5 text-sm font-medium text-danger disabled:opacity-60"
      : "rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60";

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        {verdicts.map((verdict) => (
          <button
            key={verdict.action}
            type="button"
            onClick={() => onPick(verdict)}
            disabled={busy}
            className={style(verdict.danger === true)}
          >
            {verdict.label}
          </button>
        ))}
      </div>

      {asking === null ? null : (
        <div className="flex flex-col gap-2 rounded-lg border border-ink-muted/25 p-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">{asking.reasonPrompt}</span>
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              maxLength={1000}
              className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 outline-none"
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void send(asking, reason)}
              disabled={busy || reason.trim() === ""}
              className={style(true)}
            >
              {asking.label}
            </button>
            <button
              type="button"
              onClick={() => setAsking(null)}
              disabled={busy}
              className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {message === null ? null : (
        <p role="alert" className="text-sm text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
