"use client";

import { useState } from "react";

/**
 * The generated password, shown the one time it can be read.
 *
 * It lives in that one answer and nowhere else: the row holds a hash, the journal records that
 * a password was handed over rather than which one, and no letter carries it. So the screen
 * says plainly that there is no second look — the way back is to issue another, not to go
 * looking for this one.
 */
export function HandedOverPassword({ email, password }: { email: string; password: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
    } catch {
      // no clipboard on this page — the value is on screen and can be selected by hand
      setCopied(false);
    }
  }

  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-lg border border-brand/40 bg-brand/5 p-3 text-sm"
    >
      <p>
        Пароль для <span className="font-medium">{email}</span>. Передайте его сами — в письме его
        нет, и показан он один раз.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <code className="rounded-lg border border-ink-muted/30 bg-surface px-3 py-2 font-mono tracking-wide">
          {password}
        </code>
        <button
          type="button"
          onClick={() => void copy()}
          className="rounded-lg border border-ink-muted/30 px-3 py-1.5 font-medium"
        >
          {copied ? "Скопировано" : "Скопировать"}
        </button>
      </div>
      <p className="text-ink-muted">
        По нему входят один раз: пока модератор не задаст свой пароль и не привяжет приложение,
        площадка для него закрыта. Не успеет за 72 часа — выдайте новый.
      </p>
    </div>
  );
}
