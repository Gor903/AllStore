"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { apiPost } from "@/lib/browser-api";

type TransferAdminProps = {
  userId: string;
  email: string;
};

/**
 * Hands the one administrator role to somebody else.
 *
 * There is no "make another administrator" because there is never another: the role moves as
 * a whole, in one transaction, and the person pressing this is a moderator when it returns.
 * Hence the confirmation step — this is the one button on the screen that takes something
 * away from the person pressing it.
 */
export function TransferAdmin({ userId, email }: TransferAdminProps) {
  const router = useRouter();
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onConfirm() {
    setBusy(true);
    setMessage(null);
    const result = await apiPost(`/admin/users/${userId}/transfer-admin`, {});
    setBusy(false);
    if (!result.ok) {
      setMessage(result.error.message);
      return;
    }
    setAsking(false);
    // the caller is a moderator now, so the administrator's screens are no longer theirs
    router.push("/moderation");
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => setAsking(true)}
        disabled={busy || asking}
        className="rounded-lg border border-ink-muted/30 px-3 py-1.5 text-sm font-medium disabled:opacity-60"
      >
        Передать админку
      </button>

      {!asking ? null : (
        <div className="flex flex-col gap-2 rounded-lg border border-danger/40 p-3 text-sm">
          <p>
            Передать администрирование <span className="font-medium">{email}</span>? Вы станете
            модератором и потеряете доступ к ролям, приглашениям и журналу.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void onConfirm()}
              disabled={busy}
              className="rounded-lg border border-danger/40 px-3 py-1.5 font-medium text-danger disabled:opacity-60"
            >
              Передать
            </button>
            <button
              type="button"
              onClick={() => setAsking(false)}
              disabled={busy}
              className="rounded-lg border border-ink-muted/30 px-3 py-1.5"
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {message === null ? null : (
        <p role="alert" className="max-w-xs text-xs text-danger">
          {message}
        </p>
      )}
    </div>
  );
}
